from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerRequest(BaseModel):
    """Required customer details and the message submitted to the webhook."""

    model_config = ConfigDict(str_strip_whitespace=True)

    customer_id: str = Field(min_length=1)
    customer_name: str = Field(min_length=1)
    customer_email: EmailStr
    message: str = Field(min_length=1)
