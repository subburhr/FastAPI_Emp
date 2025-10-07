from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, ForeignKey, Table, create_engine, func, text, or_, and_, case
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, timedelta
from faker import Faker
import random
import os
import json

# ----------------------------
# Database Setup
# ----------------------------
DATABASE_URL = "sqlite:///./emp_crud.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------------
# Association Tables
# ----------------------------
employee_project = Table(
    "employee_project", Base.metadata,
    Column("employee_id", ForeignKey("employees.id"), primary_key=True),
    Column("project_id", ForeignKey("projects.id"), primary_key=True)
)

employee_role = Table(
    "employee_role", Base.metadata,
    Column("employee_id", ForeignKey("employees.id"), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True)
)

# ----------------------------
# Models
# ----------------------------
class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    location = Column(String, default="HQ")
    budget = Column(Float, default=0.0)
    employees = relationship("Employee", back_populates="department")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    location = Column(String, default="HQ")
    budget = Column(Float, default=0.0)
    employees = relationship("Employee", secondary=employee_project, back_populates="projects")

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    employees = relationship("Employee", secondary=employee_role, back_populates="roles")

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer)
    email = Column(String, unique=True)
    salary = Column(Float, default=0.0)
    bonus = Column(Float, default=0.0)
    hire_date = Column(Date, default=date.today)
    active = Column(Boolean, default=True)
    gender = Column(String, default="M")
    dep_id = Column(Integer, ForeignKey("departments.id"))
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    department = relationship("Department", back_populates="employees")
    manager = relationship("Employee", remote_side=[id], backref="subordinates")
    projects = relationship("Project", secondary=employee_project, back_populates="employees")
    roles = relationship("Role", secondary=employee_role, back_populates="employees")

Base.metadata.create_all(bind=engine)

# ----------------------------
# Pydantic Schemas
# ----------------------------
class DepartmentBase(BaseModel):
    name: str
    location: Optional[str] = "HQ"
    budget: Optional[float] = 0.0

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentSchema(DepartmentBase):
    id: int
    class Config:
        orm_mode = True

class EmployeeBase(BaseModel):
    name: str
    age: Optional[int] = None
    email: Optional[str] = None
    salary: Optional[float] = 0.0
    bonus: Optional[float] = 0.0
    hire_date: Optional[date] = date.today()
    active: Optional[bool] = True
    gender: Optional[str] = "M"
    dep_id: int
    manager_id: Optional[int] = None

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeSchema(EmployeeBase):
    id: int
    department: Optional[DepartmentSchema]
    manager: Optional['EmployeeSchema'] = None
    class Config:
        orm_mode = True

EmployeeSchema.update_forward_refs()

# ----------------------------
# Repository Layer
# ----------------------------
class DepartmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self):
        return self.db.query(Department).all()

    def get_by_id(self, department_id: int):
        return self.db.query(Department).filter(Department.id == department_id).first()

    def create(self, department: DepartmentCreate):
        db_dep = Department(**department.dict())
        self.db.add(db_dep)
        self.db.commit()
        self.db.refresh(db_dep)
        return db_dep

    def delete(self, department_id: int):
        dep = self.get_by_id(department_id)
        if dep:
            self.db.delete(dep)
            self.db.commit()
        return dep

class EmployeeRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self):
        return self.db.query(Employee).all()

    def get_by_id(self, employee_id: int):
        return self.db.query(Employee).filter(Employee.id == employee_id).first()

    def create(self, employee: EmployeeCreate):
        db_emp = Employee(**employee.dict())
        self.db.add(db_emp)
        self.db.commit()
        self.db.refresh(db_emp)
        return db_emp

    def delete(self, employee_id: int):
        emp = self.get_by_id(employee_id)
        if emp:
            self.db.delete(emp)
            self.db.commit()
        return emp

# ----------------------------
# Service Layer
# ----------------------------
class DepartmentService:
    def __init__(self, db: Session):
        self.repo = DepartmentRepository(db)

    def get_all(self):
        return self.repo.get_all()

    def get_by_id(self, department_id: int):
        return self.repo.get_by_id(department_id)

    def create(self, department: DepartmentCreate):
        return self.repo.create(department)

    def delete(self, department_id: int):
        return self.repo.delete(department_id)

class EmployeeService:
    def __init__(self, db: Session):
        self.repo = EmployeeRepository(db)

    def get_all(self):
        return self.repo.get_all()

    def get_by_id(self, employee_id: int):
        return self.repo.get_by_id(employee_id)

    def create(self, employee: EmployeeCreate):
        return self.repo.create(employee)

    def delete(self, employee_id: int):
        return self.repo.delete(employee_id)

# ----------------------------
# FastAPI Setup
# ----------------------------
app = FastAPI(title="Employee & Department CRUD")
templates = Jinja2Templates(directory="templates")
query_results = []

QUERY_FILE = "stored_queries.json"

# ----------------------------
# Query Storage Utilities
# ----------------------------
def load_queries():
    if not os.path.exists(QUERY_FILE):
        with open(QUERY_FILE, "w") as f:
            json.dump([], f)
        return []
    try:
        with open(QUERY_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open(QUERY_FILE, "w") as f:
            json.dump([], f)
        return []

def save_queries(queries):
    with open(QUERY_FILE, "w") as f:
        json.dump(queries, f, indent=4)

def add_query_if_new(query: str):
    """
    Add query only if it doesn't exist.
    Assign new incremental ID.
    """
    records = load_queries()
    exists = any(r["query"].strip() == query.strip() for r in records)
    if not exists:
        new_id = max([r["id"] for r in records], default=0) + 1
        records.append({"id": new_id, "query": query.strip()})
        save_queries(records)
        return True
    return False

# ----------------------------
# Routers
# ----------------------------
employee_router = APIRouter(prefix="/employees", tags=["Employees"])
department_router = APIRouter(prefix="/departments", tags=["Departments"])
seed_router = APIRouter(tags=["Utility"])

# Employee endpoints
def get_employee_service(db: Session = Depends(get_db)):
    return EmployeeService(db)

@employee_router.get("/", response_model=List[EmployeeSchema])
def get_all_employees(service: EmployeeService = Depends(get_employee_service)):
    return service.get_all()

# Department endpoints
def get_department_service(db: Session = Depends(get_db)):
    return DepartmentService(db)

@department_router.get("/", response_model=List[DepartmentSchema])
def get_all_departments(service: DepartmentService = Depends(get_department_service)):
    return service.get_all()

# ----------------------------
# Seed Data
# ----------------------------
@seed_router.post("/seed-data", response_class=HTMLResponse)
def seed_data(n_departments: int = Form(5), n_employees: int = Form(50), db: Session = Depends(get_db)):
    fake = Faker()
    # Clear tables
    db.execute(text("DELETE FROM employee_project"))
    db.execute(text("DELETE FROM employee_role"))
    db.query(Employee).delete()
    db.query(Department).delete()
    db.query(Project).delete()
    db.query(Role).delete()
    db.commit()

    # Departments
    dep_names = ["HR","Finance","IT","Sales","Marketing","Support","Operations"]
    departments = [
        Department(name=name, budget=random.randint(50000,200000), location=random.choice(["HQ","Branch"]))
        for name in dep_names[:n_departments]
    ]
    db.add_all(departments)
    db.commit()
    dep_ids = [d.id for d in db.query(Department).all()]

    # Roles
    role_names = ["Engineer","Manager","Analyst","Admin","Intern"]
    roles = [Role(name=r) for r in role_names]
    db.add_all(roles)
    db.commit()

    # Projects
    proj_names = ["ProjectA","ProjectB","ProjectC","ProjectD"]
    projects = [
        Project(name=p, budget=random.randint(10000,50000), location=random.choice(["HQ","Branch"]))
        for p in proj_names
    ]
    db.add_all(projects)
    db.commit()

    # Employees
    employees = []
    for _ in range(n_employees):
        emp = Employee(
            name=fake.first_name(),
            age=random.randint(22,55),
            email=fake.unique.email(),
            salary=random.randint(30000,120000),
            bonus=random.randint(1000,10000),
            hire_date=date.today() - timedelta(days=random.randint(0,2000)),
            active=random.choice([True, True, True, False]),
            gender=random.choice(["M","F"]),
            dep_id=random.choice(dep_ids)
        )
        if employees:
            emp.manager_id = random.choice(employees).id

        emp.projects = random.sample(projects, k=random.randint(0,len(projects)))
        emp.roles = random.sample(roles, k=random.randint(1,len(roles)))
        employees.append(emp)

    db.add_all(employees)
    db.commit()

    html_content = f"""
    <html>
        <head>
            <meta http-equiv="refresh" content="2;url=/" />
            <style>
                body {{ background-color:#121212; color:#00FFAA; display:flex; justify-content:center; align-items:center; height:100vh; font-family:'Arial',sans-serif; flex-direction:column; text-align:center; margin:0; }}
                h2 {{ font-size:2em; margin-bottom:20px; }}
                p {{ font-size:1.2em; color:#FFD700; }}
                a {{ color:#1E90FF; text-decoration:none; font-weight:bold; }}
                a:hover {{ text-decoration:underline; }}
            </style>
        </head>
        <body>
            <h2>Seeded {n_departments} Departments & {n_employees} Employees.</h2>
            <p>You will be redirected to the home page in 2 seconds...</p>
            <p>If not, <a href="/">click here</a>.</p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ----------------------------
# Query Endpoints
# ----------------------------
@seed_router.post("/run-query")
def run_query(request: Request, query: str = Form(...), db: Session = Depends(get_db)):
    global query_results
    context = {
        "db": db,
        "Employee": Employee,
        "Department": Department,
        "Project": Project,
        "Role": Role,
        "func": func,
        "date": date,
        "timedelta": timedelta,
        "or_": or_,
        "and_": and_,
        "case": case
    }

    def serialize_row(row):
        if hasattr(row, "__dict__"):
            d = row.__dict__.copy()
            d.pop("_sa_instance_state", None)
            for k,v in d.items():
                if isinstance(v,(date,)):
                    d[k] = v.isoformat()
            return d
        elif isinstance(row, dict):
            for k,v in row.items():
                if isinstance(v,(date,)):
                    row[k] = v.isoformat()
            return row
        else:
            return {"value": str(row)}

    try:
        rows = eval(query, {}, context)
        result = []
        if isinstance(rows, list):
            for r in rows:
                result.append(serialize_row(r))
        else:
            result.append(serialize_row(rows))
        query_results.append({"query": query, "result": result, "error": None})
    except Exception as e:
        query_results.append({"query": query, "result": None, "error": str(e)})

    departments = db.query(Department).all()
    employees = db.query(Employee).all()
    stored_queries = load_queries()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "departments": departments,
        "employees": employees,
        "results": query_results,
        "stored_queries": stored_queries
    })

@seed_router.post("/save-query")
def save_query(query: str = Form(...)):
    """Save query only if new, do not replace existing."""
    added = add_query_if_new(query)
    return {"saved": added}

@seed_router.post("/update-queries")
async def update_queries(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    stored_queries = load_queries()
    # Only update query text if user modifies explicitly
    for q in stored_queries:
        key = f"query_{q['id']}"
        if key in form:
            q['query'] = form[key]
    save_queries(stored_queries)
    departments = db.query(Department).all()
    employees = db.query(Employee).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "departments": departments,
        "employees": employees,
        "results": query_results,
        "stored_queries": stored_queries
    })

@seed_router.post("/delete-query/{query_id}")
def delete_query(query_id: int, request: Request, db: Session = Depends(get_db)):
    stored_queries = load_queries()
    stored_queries = [q for q in stored_queries if q['id'] != query_id]
    save_queries(stored_queries)
    departments = db.query(Department).all()
    employees = db.query(Employee).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "departments": departments,
        "employees": employees,
        "results": query_results,
        "stored_queries": stored_queries
    })

@seed_router.post("/clear-results")
def clear_results(request: Request, db: Session = Depends(get_db)):
    global query_results
    query_results.clear()
    departments = db.query(Department).all()
    employees = db.query(Employee).all()
    stored_queries = load_queries()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "departments": departments,
        "employees": employees,
        "results": query_results,
        "stored_queries": stored_queries
    })

# ----------------------------
# Add New Query API with redirect message
# ----------------------------
from fastapi.responses import HTMLResponse

@seed_router.post("/add-query")
async def add_query(request: Request, query: str = Form(...)):
    """
    Add a new query to stored_queries.json.
    Only saves if it is not already present.
    Shows a message and redirects after 2 seconds.
    """
    added = add_query_if_new(query)

    if added:
        message = "Query added successfully!"
    else:
        message = "Query already exists, not added."

    html_content = f"""
    <html>
        <head>
            <meta http-equiv="refresh" content="1;url=/" />
            <style>
                body {{
                    background-color:#121212;
                    color:#00FFAA;
                    display:flex;
                    justify-content:center;
                    align-items:center;
                    height:100vh;
                    font-family:'Arial',sans-serif;
                    flex-direction:column;
                    text-align:center;
                    margin:0;
                }}
                h2 {{
                    font-size:2em;
                    margin-bottom:20px;
                }}
                p {{
                    font-size:1.2em;
                    color:#FFD700;
                }}
                a {{
                    color:#1E90FF;
                    text-decoration:none;
                    font-weight:bold;
                }}
                a:hover {{
                    text-decoration:underline;
                }}
            </style>
        </head>
        <body>
            <h2>{message}</h2>
            <p>You will be redirected to the home page in 2 seconds...</p>
            <p>If not, <a href="/">click here</a>.</p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)



@seed_router.get("/download-results", response_class=FileResponse)
def download_results():
    if not os.path.exists(QUERY_FILE):
        with open(QUERY_FILE, "w") as f:
            json.dump([], f, indent=4)
    return FileResponse(QUERY_FILE, media_type="application/json", filename="query_results.json")

# ----------------------------
# Home Page
# ----------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    departments = db.query(Department).all()
    employees = db.query(Employee).all()
    stored_queries = load_queries()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "departments": departments,
        "employees": employees,
        "results": query_results,
        "stored_queries": stored_queries
    })

# ----------------------------
# Include Routers
# ----------------------------
app.include_router(employee_router)
app.include_router(department_router)
app.include_router(seed_router)
