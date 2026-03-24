from app.utility.hiveMQ import HiveMQClient
from fastapi import APIRouter, Depends
from app.utility.security import get_current_user
from app.state import state

router = APIRouter(prefix="/mqtt", tags=["MQTT"])

@router.post("/publish")
async def publish_message(topic: str, message: str,
                           user = Depends(get_current_user)
                           ):
    state.mqtt_client.publish(topic, message, qos=0)
    return {"status": "Message published successfully"}