from pydantic import BaseModel

class UserInDB(BaseModel):
    uid: int
    username: str
    access_code: str

class UserCreate(BaseModel):
    username: str
    access_code: str