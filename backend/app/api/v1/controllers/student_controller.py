from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
import pandas as pd

from app.db.session import get_db
from app.models.student_model import Student
from app.schemas.student_schema import StudentCreate, StudentDashboardMetrics, StudentResponse
from app.services.csv_service import CSVService
from app.services.student_service import StudentService


router = APIRouter(prefix="/students", tags=["Students"])


@router.get("/", response_model=list[StudentResponse])
def list_students(db: Session = Depends(get_db)):
    return StudentService.list_students(db)


@router.get("/dashboard", response_model=StudentDashboardMetrics)
def get_dashboard_metrics(db: Session = Depends(get_db)):
    return StudentService.get_dashboard_metrics(db)


@router.post("/upload-csv", response_model=list[StudentResponse])
async def upload_students_csv(
    file: UploadFile = File(...),
    replace_mode: bool = Form(True),
    append_mode: bool = Form(False),
    db: Session = Depends(get_db)
):
    # File format validation
    if not file.filename.endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="❌ File Format Error: Only CSV and Excel files (.csv, .xlsx, .xls) are supported."
        )

    try:
        file_bytes = await file.read()
        
        # Check if file is empty
        if len(file_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="❌ Empty File Error: The uploaded file is empty. Please upload a file with student data."
            )
        
        students = CSVService.import_students_from_file(
            db, file_bytes, file.filename, replace_mode=replace_mode, append_mode=append_mode
        )
        
        if not students:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="❌ No Data Error: No valid students found in file. Please check the file format and ensure it contains roll_no, name, department columns."
            )
            
        return [StudentResponse.model_validate(s) for s in students]
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        error_msg = str(e)
        if "Could not find" in error_msg and "column" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"❌ Column Missing Error: {error_msg}"
            )
        elif "Failed to read file" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"❌ File Reading Error: {error_msg}. Please check if the file is corrupted or in the correct format."
            )
        elif "Failed to save students" in error_msg:
            if "Unknown column" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"❌ Database Schema Error: {error_msg}. Please contact support - database schema needs updating."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"❌ Database Save Error: {error_msg}"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"❌ Data Processing Error: {error_msg}"
            )
    except UnicodeDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="❌ File Encoding Error: Unable to read the file. Please save your CSV file with UTF-8 encoding or try uploading an Excel file instead."
        )
    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="❌ Empty Data Error: The file appears to be empty or contains no readable data."
        )
    except pd.errors.ParserError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"❌ File Parse Error: Unable to parse the file. Please check the file format. Details: {str(e)}"
        )
    except Exception as e:
        # Log the full error for debugging
        import traceback
        print(f"Unexpected error in student upload: {traceback.format_exc()}")
        
        error_str = str(e)
        if "conversation_history" in error_str:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="❌ Database Schema Error: Missing 'conversation_history' column. Please contact support to update the database schema."
            )
        elif "skills_text" in error_str:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="❌ Database Schema Error: Missing 'skills_text' column. Please contact support to update the database schema."
            )
        elif "date" in error_str:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="❌ Database Schema Error: Missing 'date' column. Please contact support to update the database schema."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"❌ Unexpected Error: {error_str}. Please try again or contact support if the issue persists."
            )


@router.put("/{student_id}", response_model=StudentResponse)
def update_student(student_id: int, data: StudentCreate, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # Update fields
    student.roll_no = data.roll_no
    student.name = data.name
    student.department = data.department.upper() if data.department else data.department
    student.domain = data.domain
    student.cgpa = data.cgpa
    student.ps_level = data.ps_level
    student.skills_text = data.skills_text
    
    db.commit()
    db.refresh(student)
    return StudentResponse.model_validate(student)


@router.delete("/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    db.delete(student)
    db.commit()
    return {"message": "Student deleted successfully"}


@router.get("/export-excel")
def export_students_excel(db: Session = Depends(get_db)):
    """Export all students to Excel file."""
    try:
        excel_bytes = CSVService.export_students_to_excel(db)
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=students.xlsx"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export students: {str(e)}"
        )


@router.get("/export-csv")
def export_students_csv(db: Session = Depends(get_db)):
    """Export all students to CSV file."""
    try:
        csv_bytes = CSVService.export_students_to_csv(db)
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=students.csv"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export students: {str(e)}"
        )


