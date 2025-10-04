from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import Optional, List
from faker import Faker
import random

# ----------------------------
# Database
# ----------------------------
DATABASE_URL = "sqlite:///./emp_crud.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------------
# Models
# ----------------------------
class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    employees = relationship("Employee", back_populates="department")

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer)
    dep_id = Column(Integer, ForeignKey("departments.id"))
    department = relationship("Department", back_populates="employees")

Base.metadata.create_all(bind=engine)

# ----------------------------
# Schemas
# ----------------------------
class DepartmentBase(BaseModel):
    name: str

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentSchema(DepartmentBase):
    id: int
    class Config:
        orm_mode = True

class EmployeeBase(BaseModel):
    name: str
    age: Optional[int] = None
    dep_id: int

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeSchema(EmployeeBase):
    id: int
    department: Optional[DepartmentSchema]
    class Config:
        orm_mode = True

# ----------------------------
# Repositories
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
# Services
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
# Routers
# ----------------------------
employee_router = APIRouter(prefix="/employees", tags=["Employees"])
department_router = APIRouter(prefix="/departments", tags=["Departments"])

def get_employee_service(db: Session = Depends(get_db)):
    return EmployeeService(db)

def get_department_service(db: Session = Depends(get_db)):
    return DepartmentService(db)

# Employee Endpoints
@employee_router.get("/", response_model=List[EmployeeSchema])
def get_all_employees(service: EmployeeService = Depends(get_employee_service)):
    return service.get_all()

@employee_router.get("/{employee_id}", response_model=EmployeeSchema)
def get_employee(employee_id: int, service: EmployeeService = Depends(get_employee_service)):
    emp = service.get_by_id(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp

@employee_router.post("/", response_model=EmployeeSchema)
def create_employee(employee: EmployeeCreate, service: EmployeeService = Depends(get_employee_service)):
    return service.create(employee)

@employee_router.delete("/{employee_id}")
def delete_employee(employee_id: int, service: EmployeeService = Depends(get_employee_service)):
    emp = service.delete(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {"detail": "Employee deleted"}

# Department Endpoints
@department_router.get("/", response_model=List[DepartmentSchema])
def get_all_departments(service: DepartmentService = Depends(get_department_service)):
    return service.get_all()

@department_router.get("/{department_id}", response_model=DepartmentSchema)
def get_department(department_id: int, service: DepartmentService = Depends(get_department_service)):
    dep = service.get_by_id(department_id)
    if not dep:
        raise HTTPException(status_code=404, detail="Department not found")
    return dep

@department_router.post("/", response_model=DepartmentSchema)
def create_department(department: DepartmentCreate, service: DepartmentService = Depends(get_department_service)):
    return service.create(department)

@department_router.delete("/{department_id}")
def delete_department(department_id: int, service: DepartmentService = Depends(get_department_service)):
    dep = service.delete(department_id)
    if not dep:
        raise HTTPException(status_code=404, detail="Department not found")
    return {"detail": "Department deleted"}

# ----------------------------
# Seed Data Endpoint
# ----------------------------
class SeedRequest(BaseModel):
    n_departments: Optional[int] = 5
    n_employees: Optional[int] = 50

seed_router = APIRouter(tags=["Utility"])

@seed_router.post("/seed-data")
def seed_data(n_departments: int = Form(5), n_employees: int = Form(50), db: Session = Depends(get_db)):
    fake = Faker()
    db.query(Employee).delete()
    db.query(Department).delete()
    db.commit()

    dep_names = ["HR","Finance","IT","Sales","Marketing","Support","Operations"]
    departments = [Department(name=name) for name in dep_names[:n_departments]]
    db.add_all(departments)
    db.commit()

    dep_ids = [d.id for d in db.query(Department).all()]

    employees = []
    for _ in range(n_employees):
        employees.append(Employee(
            name=fake.first_name(),
            age=random.randint(22,55),
            dep_id=random.choice(dep_ids)
        ))
    db.add_all(employees)
    db.commit()
    return {"detail": f"Seeded {n_departments} Departments & {n_employees} Employees"}

# ----------------------------
# Templates
# ----------------------------
templates = Jinja2Templates(directory="templates")

# Store query results
query_results = []

@seed_router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    departments = db.query(Department).all()
    employees = db.query(Employee).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "departments": departments,
        "employees": employees,
        "results": query_results
    })

@seed_router.post("/run-query")
def run_query(request: Request, query: str = Form(...), db: Session = Depends(get_db)):
    global query_results
    # Split multiple queries by newline
    queries = [q.strip() for q in query.splitlines() if q.strip()]
    for q in queries:
        try:
            # Evaluate ORM query (admin only, trusted input)
            rows = eval(q)  # ⚠ Only trusted queries
            result = []
            for r in rows:
                if hasattr(r, '__dict__'):
                    d = r.__dict__.copy()
                    d.pop('_sa_instance_state', None)
                    result.append(d)
                elif isinstance(r, dict):
                    result.append(r)
                else:
                    result.append({"value": str(r)})
            query_results.append({"query": q, "result": result, "error": None})
        except Exception as e:
            query_results.append({"query": q, "result": None, "error": str(e)})

    departments = db.query(Department).all()
    employees = db.query(Employee).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "departments": departments,
        "employees": employees,
        "results": query_results
    })


@seed_router.post("/clear-results")
def clear_results(request: Request, db: Session = Depends(get_db)):
    global query_results
    query_results.clear()
    departments = db.query(Department).all()
    employees = db.query(Employee).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "departments": departments,
        "employees": employees,
        "results": query_results
    })

# ----------------------------
# FastAPI App
# ----------------------------
fastapi_app = FastAPI(title="Employee & Department CRUD")
fastapi_app.include_router(employee_router)
fastapi_app.include_router(department_router)
fastapi_app.include_router(seed_router)
