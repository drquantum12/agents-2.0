import os
import paho.mqtt.client as paho
from paho import mqtt
import asyncio

# qos 0 - at most once
# qos 1 - at least once
# qos 2 - exactly once

class HiveMQClient:
    def __init__(self):
        self.broker = os.getenv("HiveMQ_HOST")
        self.port = int(os.getenv("HiveMQ_PORT", 8883))
        self.username = os.getenv("HiveMQ_USERNAME")
        self.password = os.getenv("HiveMQ_PASSWORD")
        self.client = paho.Client(client_id="", userdata=None, protocol=paho.MQTTv5)
        if self.username and self.password:
            self.client.tls_set(tls_version=mqtt.client.ssl.PROTOCOL_TLS)
            self.client.username_pw_set(self.username, self.password)

    async def connect(self):
        await asyncio.to_thread(self.client.connect, self.broker, self.port)
        self.client.loop_start()
        print(f"Connected to MQTT broker at {self.broker}:{self.port}")

    def publish(self, topic, payload, qos=0):
        result = self.client.publish(topic, payload, qos=qos)
        status = result[0]
        if status == 0:
            print(f"Sent `{payload}` to topic `{topic}`")
        else:
            print(f"Failed to send message to topic {topic}")

    async def disconnect(self):
        self.client.loop_stop()
        await asyncio.to_thread(self.client.disconnect)