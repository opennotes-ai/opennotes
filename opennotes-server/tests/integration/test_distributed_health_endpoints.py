from src.config import settings


def test_distributed_health_endpoint(client) -> None:
    response = client.get("/health/distributed")

    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "instance_count" in data
    assert "healthy_instances" in data
    assert "degraded_instances" in data
    assert "unhealthy_instances" in data
    assert "instances" in data
    assert isinstance(data["instances"], dict)


def test_instances_health_endpoint(client) -> None:
    response = client.get("/health/instances")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, dict)


def test_instance_health_endpoint_current_instance(client) -> None:
    instance_id = settings.INSTANCE_ID
    response = client.get(f"/health/instances/{instance_id}")

    if response.status_code == 200:
        data = response.json()
        assert data["instance_id"] == instance_id
    elif response.status_code == 404:
        pass


def test_instance_health_endpoint_not_found(client) -> None:
    response = client.get("/health/instances/nonexistent-instance-99999")

    assert response.status_code == 404


def test_distributed_health_aggregation(client) -> None:
    response = client.get("/health/distributed")

    assert response.status_code == 200
    data = response.json()

    total_instances = (
        data["healthy_instances"] + data["degraded_instances"] + data["unhealthy_instances"]
    )
    assert total_instances == data["instance_count"]


def test_distributed_health_status_consistency(client) -> None:
    response = client.get("/health/distributed")

    assert response.status_code == 200
    data = response.json()

    status = data["status"]
    _healthy_count = data["healthy_instances"]
    degraded_count = data["degraded_instances"]
    unhealthy_count = data["unhealthy_instances"]

    if unhealthy_count > 0:
        assert status == "unhealthy"
    elif degraded_count > 0:
        assert status == "degraded"
    else:
        assert status == "healthy"


def test_instances_endpoint_returns_dict(client) -> None:
    response = client.get("/health/instances")

    assert response.status_code == 200
    data = response.json()

    for instance_id, instance_data in data.items():
        assert isinstance(instance_id, str)
        assert isinstance(instance_data, dict)
        assert "instance_id" in instance_data
        assert "status" in instance_data
        assert "last_heartbeat" in instance_data
        assert "time_since_heartbeat_seconds" in instance_data
