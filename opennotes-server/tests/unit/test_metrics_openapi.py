from src.main import app


def test_metrics_endpoint_declares_text_plain():
    schema = app.openapi()
    metrics_get = schema["paths"]["/metrics"]["get"]
    assert "200" in metrics_get["responses"]
    content = metrics_get["responses"]["200"]["content"]
    assert "text/plain" in content
    assert content["text/plain"]["schema"]["type"] == "string"


def test_metrics_endpoint_declares_404():
    schema = app.openapi()
    metrics_get = schema["paths"]["/metrics"]["get"]
    assert "404" in metrics_get["responses"]
