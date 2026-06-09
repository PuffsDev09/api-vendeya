from pydantic import BaseModel

class SetCodeRequest(BaseModel):
    code: str
    ids: list


