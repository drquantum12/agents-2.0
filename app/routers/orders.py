# router for razorpay orders
from fastapi import APIRouter, HTTPException, Depends, Request
from app.schemas.orders import CreateOrderRequest, VerifyPaymentRequest, OrderResponse, NotifyOnNewDeviceRequest
from app.email_engine import send_preorder_confirmation_email, send_notify_new_device_email
import razorpay, hmac, hashlib, resend
import os, time, json
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient

router = APIRouter(
    prefix="/orders",
    tags=["orders"]
)

client = razorpay.Client(auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET")))

def get_db():
    client = AsyncIOMotorClient(os.getenv("MONGODB_CONNECTION_STRING"))
    db = client["neurosattva"]
    return db

@router.post("/create")
async def create_order(order_request: CreateOrderRequest,
                    db=Depends(get_db)):
    # create razorpay order
    receipt_id = f"rcpt_{order_request.email.split('@')[0][:8]}_{int(time.time())}"

    rz_order = client.order.create({
        "amount": order_request.amount * 100,  # amount in paise
        "currency": "INR",
        "receipt": receipt_id,
        "notes": {
            "product_id": order_request.product_id,
            "order_type": order_request.order_type,
            "email": order_request.email
        }
    })

    # save order details in db
    await db.orders.insert_one({
        "razorpay_order_id": rz_order["id"],
        "name": order_request.name,
        "email": order_request.email,
        "phone": order_request.phone,
        "product_id": order_request.product_id,
        "amount": order_request.amount,
        "order_type": order_request.order_type,
        "status": "pending",
        "house_no": order_request.house_no,
        "locality": order_request.locality,
        "city": order_request.city,
        "state": order_request.state,
        "pincode": order_request.pincode,
        "created_at": time.time(),
        "updated_at": time.time()
    })
    return {"order_id": rz_order["id"], "amount": order_request.amount, "currency": "INR"}


@router.post("/verify")
async def verify_payment(verify_request: VerifyPaymentRequest,
                        db=Depends(get_db)):
    # Signature verification — confirms checkout completed and response is untampered
    msg = f"{verify_request.order_id}|{verify_request.payment_id}"
    expected_signature = hmac.new(
        os.getenv("RAZORPAY_KEY_SECRET").encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected_signature != verify_request.signature:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # save payment_id and mark as processing only if still pending —
    # webhook may have already set status to "paid" before verify is called
    await db.orders.update_one(
        {"razorpay_order_id": verify_request.order_id, "status": "pending"},
        {"$set": {"payment_id": verify_request.payment_id, "status": "processing", "updated_at": time.time()}}
    )
    return {"success": True, "status": "processing"}


@router.get("/status/{order_id}")
async def get_order_status(order_id: str, db=Depends(get_db)):
    order = await db.orders.find_one({"razorpay_order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"status": order["status"], "order": order if order["status"] in ("paid", "failed") else None}


# webhook endpoint to handle payment failures and refunds
@router.post("/webhook")
async def razorpay_webhook(request: Request, db=Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    expected_signature = hmac.new(
        os.getenv("RAZORPAY_WEBHOOK_SECRET").encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if expected_signature != signature:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = json.loads(payload)
    if event["event"] == "payment.captured":
        razorpay_order_id = event["payload"]["payment"]["entity"]["order_id"]
        # update order status to paid
        await db.orders.update_one(
            {"razorpay_order_id": razorpay_order_id},
            {"$set": {"status": "paid", "updated_at": time.time()}})

        # send preorder confirmation email using email stored on the order
        order = await db.orders.find_one({"razorpay_order_id": razorpay_order_id})
        if order and order.get("email"):
            send_preorder_confirmation_email(order["email"], {
                "name": order.get("name", order.get("email").split("@")[0]),
                "order_id": razorpay_order_id,
                "address_flat": order.get("house_no", ""),
                "address_street": order.get("locality", ""),
                "address_city": order.get("city", ""),
                "address_pin": order.get("pincode", ""),
                "address_state": order.get("state", ""),
            })

    elif event["event"] == "payment.failed":
        # update order status to failed
        await db.orders.update_one(
            {"razorpay_order_id": event["payload"]["payment"]["entity"]["order_id"]},
            {"$set": {"status": "failed", "updated_at": time.time()}}
        )
    elif event["event"] == "refund.processed":
        # update order status to refunded
        await db.orders.update_one(
            {"razorpay_order_id": event["payload"]["refund"]["entity"]["order_id"]},
            {"$set": {"status": "refunded", "updated_at": time.time()}}
        )
    return {"success": True}


@router.get("/get/{email}", response_model=List[OrderResponse])
async def get_orders_by_email(email: str, db=Depends(get_db)):
    cursor = db.orders.find({"email": email}, {"_id": 0})
    orders = await cursor.to_list(length=None)
    return orders


@router.post("/notify-on-new-device")
async def notify_on_new_device(body: NotifyOnNewDeviceRequest, db=Depends(get_db)):
    email = body.email
    user = await db.potential_customers.find_one({"email": email})

    if user:
        return {"success": True, "message": "Already registered for notifications"}
    
    customer = await db.potential_customers.insert_one({
        "name": body.name,
        "email": body.email,
        "city": body.city,
        "state": body.state,
        "trigger_point": "notify on new device",
        "created_at": time.time()
    })
    if customer.inserted_id:
        send_notify_new_device_email(body.email, {"name": body.name, "city": body.city, "state": body.state})

    return {"success": True}