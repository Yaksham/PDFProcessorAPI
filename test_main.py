import time
from fastapi.testclient import TestClient

from main import app, convert_pdf, API_KEY

client = TestClient(app)

def test_receive_pdf():
    pdf_content = b"PDF"
    files = {'file': ('test.pdf', pdf_content, 'application/pdf')}
    headers = {'api_key': API_KEY}
    response = client.post("/webhook/", files=files, headers=headers)
    assert response.status_code == 200
    json_response = response.json()
    assert "file_id" in json_response

def test_receive_pdf_invalid():
    non_pdf_content = b"Not a PDF"
    files = {'file': ('test.txt', non_pdf_content, 'text/plain')}
    headers = {'api_key': API_KEY}
    response = client.post("/webhook/", files=files, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded file is not a valid PDF file."
    
def test_polling_unknown_file():
    headers = {'api_key': API_KEY}
    response = client.get("/polling/random_id", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"

def test_polling():
    # Use the same setup as in test_receive_pdf to get a file_id
    pdf_content = b"PDF"
    files = {'file': ('test.pdf', pdf_content, 'application/pdf')}
    headers = {'api_key': API_KEY}
    response = client.post("/webhook/", files=files, headers=headers)
    json_response = response.json()
    file_id = json_response["file_id"]
    convert_pdf(file_id)
    
    # Wait for the Celery task to complete (polling 5 times)
    for _ in range(5):
        response = client.get(f"/polling/{file_id}", headers=headers)
        json_response = response.json()
        if "data" in json_response:
            break
        time.sleep(0.1)
    
    assert response.status_code == 200
    assert "data" in json_response
    
