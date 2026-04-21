from app.utility.hiveMQ import HiveMQClient
from fastapi import APIRouter, Depends
from app.utility.security import get_current_user
from app.state import state
from pydantic import BaseModel

router = APIRouter(prefix="/mqtt", tags=["MQTT"])

class MQTTMessage(BaseModel):
    topic: str
    message: str
    qos: int = 0  # Quality of Service level (0, 1, or 2)


@router.post("/publish")
async def publish_message(message: MQTTMessage,
                           user = Depends(get_current_user)
                           ):
    state.mqtt_client.publish(message.topic, message.message, qos=message.qos)
    return {"status": "Message published successfully"}