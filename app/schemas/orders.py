# schema for razorpay orders
from pydantic import BaseModel, EmailStr

class Orders(BaseModel):
    _id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    email: str
    phone: str
    product_id: str
    amount: int
    order_type: str
    status: str
    created_at: float
    updated_at: float

class OrderResponse(BaseModel):
    razorpay_order_id: str
    email: str
    phone: str | None = None
    product_id: str
    amount: int
    order_type: str
    status: str
    payment_id: str | None = None
    house_no: str | None = None
    locality: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    created_at: float
    updated_at: float

class CreateOrderRequest(BaseModel):
    amount: int
    product_id: str
    order_type: str
    name: str
    email: EmailStr
    phone: str
    house_no: str
    locality: str
    city: str
    state: str
    pincode: str

class VerifyPaymentRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str

class NotifyOnNewDeviceRequest(BaseModel):
    name: str
    email: EmailStr
    city: str | None = None
    state: str | None = None