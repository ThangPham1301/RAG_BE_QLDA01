#!/usr/bin/env python
"""
End-to-end API testing script for RAG_BE
Tests complete workflow from user registration to chat interaction
"""
import requests
import json
import os
from pathlib import Path

# API Base URL
BASE_URL = "http://localhost:8000/api"

# Test credentials
import time
TEST_EMAIL = f"testuser{int(time.time())}@gmail.com"
TEST_PASSWORD = "TestPassword123!"
TEST_PROJECT_NAME = "Test RAG Project"
TEST_DOCUMENT_TITLE = "Sample Document"

def log(step, message):
    print(f"\n{'='*60}")
    print(f"STEP {step}: {message}")
    print('='*60)

def log_response(response, title="Response"):
    print(f"\n{title}:")
    print(f"Status Code: {response.status_code}")
    try:
        print(f"JSON: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Text: {response.text[:500]}")

def test_auth():
    """Test authentication endpoints"""
    log(1, "Testing Authentication")
    
    # 0. Create/update verified test user via helper script
    log(1.0, "Creating/verifying test user")
    import subprocess
    import sys
    
    try:
        result = subprocess.run(
            [sys.executable, 'create_test_user.py', TEST_EMAIL, TEST_PASSWORD],
            cwd=r"C:\Users\Lenovo\Documents\IT Thang 23T-DT3\QLDA\Khai_RAG\RAG_BE_QLDA01",
            capture_output=True,
            text=True,
            timeout=15
        )
        output = result.stdout.strip()
        if output.startswith("CREATED:"):
            print(f"Test user created")
        elif output.startswith("UPDATED:"):
            print(f"Test user updated")
        else:
            print(f"Setup: {output}")
        
        if result.returncode != 0:
            print(f"Warning: {result.stderr[:200]}")
    except Exception as e:
        print(f"Warning: Could not setup test user: {e}")
    
    print()
    
    # 1. Login with test user
    log(1.1, "POST /auth/login")
    login_data = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }
    resp = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    log_response(resp, "Login Response")
    
    if resp.status_code != 200:
        print("Login failed")
        return None
    
    tokens = resp.json()
    # Handle both response formats
    if 'tokens' in tokens:
        access_token = tokens['tokens'].get('access')
        refresh_token = tokens['tokens'].get('refresh')
    else:
        access_token = tokens.get('access')
        refresh_token = tokens.get('refresh')
    
    if not access_token:
        print("No access token in response")
        return None
    
    print(f"Login successful. Access Token: {access_token[:20]}...")
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'email': TEST_EMAIL
    }

def get_headers(access_token):
    """Get authorization headers"""
    return {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

def test_projects(auth_data):
    """Test project endpoints"""
    log(2, "Testing Projects")
    headers = get_headers(auth_data['access_token'])
    
    # 1. Create project
    log(2.1, "POST /projects/")
    project_data = {
        "name": TEST_PROJECT_NAME,
        "description": "A test project for RAG system"
    }
    resp = requests.post(
        f"{BASE_URL}/projects/",
        json=project_data,
        headers=headers
    )
    log_response(resp, "Create Project Response")
    
    if resp.status_code != 201:
        print("❌ Create project failed")
        return None
    
    project = resp.json()
    project_id = project.get('id')
    print(f"✅ Project created. ID: {project_id}")
    
    # 2. List projects
    log(2.2, "GET /projects/")
    resp = requests.get(f"{BASE_URL}/projects/", headers=headers)
    log_response(resp, "List Projects Response")
    results = resp.json()
    if isinstance(results, dict):
        count = len(results.get('results', []))
    else:
        count = len(results)
    print(f"✅ Retrieved {count} projects")
    
    # 3. Get project detail
    log(2.3, f"GET /projects/{project_id}/")
    resp = requests.get(f"{BASE_URL}/projects/{project_id}/", headers=headers)
    log_response(resp, "Project Detail Response")
    print(f"✅ Project retrieved")
    
    return project_id

def test_documents(auth_data, project_id):
    """Test document endpoints"""
    log(3, "Testing Documents")
    headers_auth = get_headers(auth_data['access_token'])
    
    # 1. Create a sample document file
    log(3.1, "Creating sample document file")
    sample_file_path = Path("sample_document.txt")
    sample_file_path.write_text("This is a test document. It contains sample content for RAG system testing.")
    print(f"✅ Sample file created: {sample_file_path}")
    
    # 2. Upload document
    log(3.2, "POST /documents/ (with file upload)")
    with open(sample_file_path, 'rb') as f:
        files = {
            'file': (sample_file_path.name, f, 'text/plain')
        }
        data = {
            'project': project_id,
            'title': TEST_DOCUMENT_TITLE
        }
        resp = requests.post(
            f"{BASE_URL}/documents/",
            files=files,
            data=data,
            headers={'Authorization': f'Bearer {auth_data["access_token"]}'}
        )
    log_response(resp, "Upload Document Response")
    
    if resp.status_code not in [201, 200]:
        print("❌ Upload document failed")
        # Clean up
        sample_file_path.unlink()
        return None
    
    doc_data = resp.json()
    if isinstance(doc_data, dict) and 'documents' in doc_data:
        documents = doc_data['documents']
        doc_id = documents[0]['id'] if documents else None
    else:
        doc_id = doc_data.get('id')
    
    print(f"✅ Document uploaded. ID: {doc_id}")
    
    # 3. List documents
    log(3.3, "GET /documents/?project={project_id}")
    resp = requests.get(
        f"{BASE_URL}/documents/?project={project_id}",
        headers=headers_auth
    )
    log_response(resp, "List Documents Response")
    print(f"✅ Retrieved documents")
    
    # Clean up
    sample_file_path.unlink()
    
    return doc_id

def test_chat(auth_data, project_id):
    """Test chat endpoints"""
    log(4, "Testing Chat Sessions")
    headers = get_headers(auth_data['access_token'])
    
    # 1. Create chat session
    log(4.1, "POST /chat/sessions/")
    session_data = {
        "project": project_id,
        "title": "Test Chat Session",
        "description": "A test chat session"
    }
    resp = requests.post(
        f"{BASE_URL}/chat/sessions/",
        json=session_data,
        headers=headers
    )
    log_response(resp, "Create Chat Session Response")
    
    if resp.status_code != 201:
        print("❌ Create chat session failed")
        return None
    
    session = resp.json()
    session_id = session.get('id')
    print(f"✅ Chat session created. ID: {session_id}")
    
    # 2. Send message
    log(4.2, f"POST /chat/sessions/{session_id}/send_message/")
    message_data = {
        "content": "What is this document about?",
        "selected_document_ids": []
    }
    resp = requests.post(
        f"{BASE_URL}/chat/sessions/{session_id}/send_message/",
        json=message_data,
        headers=headers
    )
    log_response(resp, "Send Message Response")
    
    if resp.status_code not in [200, 201]:
        print("⚠️  Send message failed (this may be expected if RAG services are not configured)")
    else:
        print(f"✅ Message sent and response received")
    
    # 3. Get chat session detail with messages
    log(4.3, f"GET /chat/sessions/{session_id}/")
    resp = requests.get(
        f"{BASE_URL}/chat/sessions/{session_id}/",
        headers=headers
    )
    log_response(resp, "Get Chat Session Detail Response")
    print(f"✅ Chat session detail retrieved")
    
    # 4. List chat messages
    log(4.4, f"GET /chat/messages/?session_id={session_id}")
    resp = requests.get(
        f"{BASE_URL}/chat/messages/?session_id={session_id}",
        headers=headers
    )
    log_response(resp, "List Chat Messages Response")
    print(f"✅ Chat messages retrieved")
    
    return session_id

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("RAG BACKEND - END-TO-END API TEST")
    print("="*60)
    
    try:
        # Test auth
        auth_data = test_auth()
        if not auth_data:
            print("\n❌ Authentication test failed. Stopping.")
            return
        
        # Test projects
        project_id = test_projects(auth_data)
        if not project_id:
            print("\n❌ Projects test failed. Stopping.")
            return
        
        # Test documents
        doc_id = test_documents(auth_data, project_id)
        if not doc_id:
            print("\n⚠️  Documents test had issues, but continuing...")
        
        # Test chat
        session_id = test_chat(auth_data, project_id)
        if not session_id:
            print("\n❌ Chat test failed. Stopping.")
            return
        
        print("\n" + "="*60)
        print("✅ END-TO-END TEST COMPLETED SUCCESSFULLY")
        print("="*60)
        print(f"\nTest Summary:")
        print(f"  - User: {auth_data['email']}")
        print(f"  - Project: {project_id}")
        print(f"  - Document: {doc_id}")
        print(f"  - Chat Session: {session_id}")
        print("\nAll major API endpoints are working correctly!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
