import io
from unittest.mock import MagicMock, patch

import pytest

from app import s3_client


def test_content_disposition_escapes_quotes():
    header = s3_client.content_disposition_for_filename('evil"; filename="malware.exe')
    assert 'filename="evil\'; filename=\'malware.exe"' in header
    assert "filename*=UTF-8''" in header


def test_empty_upload_uses_put_object():
    mock_client = MagicMock()
    with patch.object(s3_client, "_client", return_value=mock_client):
        digest, size = s3_client.upload_fileobj(
            io.BytesIO(b""), "bucket", "key", "text/plain", 1024
        )

    assert size == 0
    assert digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    mock_client.put_object.assert_called_once_with(
        Bucket="bucket", Key="key", Body=b"", ContentType="text/plain"
    )
    mock_client.create_multipart_upload.assert_not_called()


def test_non_empty_upload_uses_multipart():
    mock_client = MagicMock()
    mock_client.create_multipart_upload.return_value = {"UploadId": "upload-1"}
    mock_client.upload_part.return_value = {"ETag": '"etag-1"'}

    with patch.object(s3_client, "_client", return_value=mock_client):
        digest, size = s3_client.upload_fileobj(
            io.BytesIO(b"hello"), "bucket", "key", "text/plain", 1024
        )

    assert size == 5
    assert len(digest) == 64
    mock_client.put_object.assert_not_called()
    mock_client.complete_multipart_upload.assert_called_once()


def test_upload_aborts_multipart_on_oversize():
    mock_client = MagicMock()
    mock_client.create_multipart_upload.return_value = {"UploadId": "upload-1"}
    mock_client.upload_part.return_value = {"ETag": '"etag-1"'}

    with patch.object(s3_client, "_client", return_value=mock_client):
        with pytest.raises(s3_client.FileTooLargeError):
            s3_client.upload_fileobj(io.BytesIO(b"x" * 10), "bucket", "key", "text/plain", 5)

    mock_client.abort_multipart_upload.assert_called_once()
