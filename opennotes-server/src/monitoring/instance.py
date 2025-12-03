import os
import socket
from typing import Any, Optional


class InstanceMetadata:
    _instance: Optional["InstanceMetadata"] = None

    @classmethod
    def set_instance(cls, metadata: "InstanceMetadata") -> None:
        cls._instance = metadata

    @classmethod
    def get_instance(cls) -> Optional["InstanceMetadata"]:
        return cls._instance

    @classmethod
    def get_instance_id(cls) -> str:
        if cls._instance:
            return cls._instance._instance_id
        return "unknown"

    @classmethod
    def get_hostname(cls) -> str:
        if cls._instance:
            return cls._instance._hostname
        return socket.gethostname()

    @classmethod
    def instance_id(cls) -> str:
        if cls._instance:
            return cls._instance._instance_id
        return "unknown"

    @classmethod
    def hostname(cls) -> str:
        if cls._instance:
            return cls._instance._hostname
        return socket.gethostname()

    def __init__(
        self,
        instance_id: str,
        hostname: str | None = None,
        pod_name: str | None = None,
        environment: str | None = None,
    ) -> None:
        self._instance_id = instance_id
        self._hostname = hostname or socket.gethostname()
        self.pod_name = pod_name or os.getenv("HOSTNAME", "")
        self.environment = environment or os.getenv("ENVIRONMENT", "development")

    def __getattribute__(self, name: str) -> Any:
        if name == "instance_id":
            return object.__getattribute__(self, "_instance_id")
        if name == "hostname":
            return object.__getattribute__(self, "_hostname")
        return object.__getattribute__(self, name)

    def to_dict(self) -> dict[str, str]:
        return {
            "instance_id": self._instance_id,
            "hostname": self._hostname,
            "pod_name": self.pod_name or "",
            "environment": self.environment or "",
        }


def initialize_instance_metadata(
    instance_id: str,
    environment: str | None = None,
) -> InstanceMetadata:
    metadata = InstanceMetadata(
        instance_id=instance_id,
        environment=environment,
    )
    InstanceMetadata.set_instance(metadata)
    return metadata
