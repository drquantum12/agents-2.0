from sarvamai import SarvamAI, AsyncSarvamAI
from app.utility.hiveMQ import HiveMQClient

class GlobalState:
    async_sarvam_client: AsyncSarvamAI = None
    sarvam_client: SarvamAI = None
    mqtt_client: HiveMQClient = None


state = GlobalState()
