"""Image attachments stay session-scoped and become multimodal only for model calls."""
import base64

import pytest

from agent.images import ImageError, model_messages, read_image, save_image, validate_images
from agent.config import Endpoint
from agent.http import HttpError
from agent.llm import LLMClient, LLMError


PNG = b"\x89PNG\r\n\x1a\n" + b"test-image"


def test_image_refs_and_model_payload(tmp_path):
    image_id = save_image(tmp_path, "s-test", PNG)
    assert read_image(tmp_path, "s-test", image_id) == (PNG, "image/png")
    assert validate_images(tmp_path, "s-test", [image_id]) == [image_id]
    original = [{"role": "user", "content": "看看", "images": [image_id]}]
    payload = model_messages(original, tmp_path, "s-test")
    assert original[0]["content"] == "看看"  # 归档/检查点仍只存图片编号
    assert payload[0]["content"][0] == {"type": "text", "text": "看看"}
    assert payload[0]["content"][1]["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(PNG).decode()


def test_image_validation_is_session_scoped(tmp_path):
    image_id = save_image(tmp_path, "s-one", PNG)
    with pytest.raises(ImageError):
        validate_images(tmp_path, "s-two", [image_id])
    with pytest.raises(ImageError):
        validate_images(tmp_path, "s-one", [image_id, image_id])
    with pytest.raises(ImageError):
        read_image(tmp_path, "s-one", "../other")
    with pytest.raises(ImageError):
        save_image(tmp_path, "s-one", b"not an image")


def test_provider_error_does_not_echo_image_data(monkeypatch):
    def bad_response(*args, **kwargs):
        raise HttpError(400, "unsupported data:image/png;base64,QUJDREVGRw==")

    monkeypatch.setattr("agent.llm.post_json", bad_response)
    client = LLMClient(Endpoint(name="local", base_url="http://127.0.0.1", model="fake"))
    with pytest.raises(LLMError, match="图片数据") as err:
        client.chat([{"role": "user", "content": "看看"}])
    assert "QUJDREVGRw==" not in str(err.value)
