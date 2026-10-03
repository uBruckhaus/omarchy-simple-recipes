from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app

def test_api_youtube_search_empty():
    client = TestClient(app)

    # 1. Empty query returns empty list
    response = client.get("/api/youtube/search?q=")
    assert response.status_code == 200
    assert response.json() == []

    # 2. Query with spaces returns empty list
    response = client.get("/api/youtube/search?q=   ")
    assert response.status_code == 200
    assert response.json() == []

def test_api_youtube_search_mocked():
    client = TestClient(app)

    # Mock yt-dlp response
    mock_result = {
        "entries": [
            {
                "id": "abc123xyz",
                "title": "Super Leckere Lasagne",
                "url": "https://www.youtube.com/watch?v=abc123xyz",
                "duration": 586,
                "channel": "Kochen Mit Spass",
                "thumbnails": [{"url": "https://example.com/thumb.jpg"}]
            }
        ]
    }

    with patch("yt_dlp.YoutubeDL") as mock_ydl_class:
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = mock_result
        mock_ydl_class.return_value.__enter__.return_value = mock_instance

        response = client.get("/api/youtube/search?q=lasagne")
        assert response.status_code == 200
        
        results = response.json()
        assert len(results) == 1
        assert results[0]["id"] == "abc123xyz"
        assert results[0]["title"] == "Super Leckere Lasagne"
        assert results[0]["duration"] == "9:46"
        assert results[0]["channel"] == "Kochen Mit Spass"
        assert results[0]["thumbnail"] == "https://example.com/thumb.jpg"
