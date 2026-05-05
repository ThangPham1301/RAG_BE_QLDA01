# 📱 HƯỚNG DẪN TEST API BẰNG POSTMAN

## 🚀 Chuẩn Bị

### 1. Khởi Động Server
Server Django đang chạy trên: **http://localhost:8000**

Để kiểm tra, mở browser và truy cập:
```
http://localhost:8000/admin/
```

### 2. Import Collection vào Postman
Các endpoint API sẵn sàng để test bằng Postman.

---

## 📋 DANH SÁCH ENDPOINT

### 🔐 AUTHENTICATION (Xác Thực)

#### 1️⃣ **SIGNUP - Đăng Ký Tài Khoản**
```
POST http://localhost:8000/api/auth/signup
Content-Type: application/json

Body (JSON):
{
  "email": "testuser@gmail.com",
  "password": "TestPassword123!",
  "password_confirm": "TestPassword123!",
  "first_name": "Test",
  "last_name": "User"
}

Response: 201 Created
{
  "message": "Sign up successful. Please check your email to verify your account.",
  "user": {
    "id": "uuid",
    "email": "testuser@gmail.com",
    "is_email_verified": false
  }
}
```

#### 2️⃣ **LOGIN - Đăng Nhập**
```
POST http://localhost:8000/api/auth/login
Content-Type: application/json

Body (JSON):
{
  "email": "testuser@gmail.com",
  "password": "TestPassword123!"
}

Response: 200 OK
{
  "message": "Login successful",
  "tokens": {
    "access": "eyJhbGciOiJIUzI1NiIs...",  <- COPY CÁI NÀY
    "refresh": "eyJhbGciOiJIUzI1NiIs..."
  }
}
```
⚠️ **Sau bước này, copy token `access` để dùng cho các request tiếp theo**

#### 3️⃣ **GET CURRENT USER - Lấy Thông Tin User Hiện Tại**
```
GET http://localhost:8000/api/auth/me

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
{
  "id": "uuid",
  "email": "testuser@gmail.com",
  "first_name": "Test",
  "last_name": "User"
}
```

---

### 📁 PROJECTS (Dự Án)

#### 4️⃣ **CREATE PROJECT - Tạo Dự Án**
```
POST http://localhost:8000/api/projects/
Content-Type: application/json

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Body (JSON):
{
  "name": "Dự Án RAG Test",
  "description": "Project để test RAG system"
}

Response: 201 Created
{
  "id": 1,
  "name": "Dự Án RAG Test",
  "description": "Project để test RAG system",
  "owner": "uuid",
  "owner_email": "testuser@gmail.com",
  "documents_count": 0,
  "chats_count": 0,
  "created_at": "2026-05-03T14:30:00Z",
  "updated_at": "2026-05-03T14:30:00Z"
}
```
⚠️ **Save project ID (1 trong ví dụ) để dùng ở các bước tiếp theo**

#### 5️⃣ **LIST PROJECTS - Danh Sách Dự Án**
```
GET http://localhost:8000/api/projects/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
[
  {
    "id": 1,
    "name": "Dự Án RAG Test",
    ...
  }
]
```

#### 6️⃣ **GET PROJECT DETAIL - Chi Tiết Dự Án**
```
GET http://localhost:8000/api/projects/1/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
{
  "id": 1,
  "name": "Dự Án RAG Test",
  ...
}
```

#### 7️⃣ **GET PROJECT DOCUMENTS - Danh Sách Tài Liệu**
```
GET http://localhost:8000/api/projects/1/documents/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
[
  {
    "id": 1,
    "title": "Document 1",
    ...
  }
]
```

#### 8️⃣ **GET PROJECT CHATS - Danh Sách Chat**
```
GET http://localhost:8000/api/projects/1/chats/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
[
  {
    "id": 1,
    "title": "Chat 1",
    ...
  }
]
```

---

### 📄 DOCUMENTS (Tài Liệu)

#### 9️⃣ **UPLOAD DOCUMENT - Tải Lên Tài Liệu**
```
POST http://localhost:8000/api/documents/
Content-Type: multipart/form-data

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Form Data:
- project: 1  (ID của project vừa tạo)
- title: "Tài Liệu Test"
- file: <Select file> (PDF, DOCX, TXT)

Response: 201 Created
{
  "documents": [
    {
      "id": 1,
      "title": "Tài Liệu Test",
      "file_type": "pdf",
      "index_status": "pending",
      "uploaded_at": "2026-05-03T14:35:00Z"
    }
  ]
}
```

#### 🔟 **LIST DOCUMENTS - Danh Sách Tài Liệu**
```
GET http://localhost:8000/api/documents/?project=1

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
[
  {
    "id": 1,
    "title": "Tài Liệu Test",
    ...
  }
]
```

#### 1️⃣1️⃣ **GET DOCUMENT DETAIL - Chi Tiết Tài Liệu**
```
GET http://localhost:8000/api/documents/1/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
{
  "id": 1,
  "title": "Tài Liệu Test",
  "index_status": "indexed",
  "indexed_chunks": 5,
  ...
}
```

#### 1️⃣2️⃣ **REINDEX DOCUMENT - Chỉ Mục Lại Tài Liệu**
```
POST http://localhost:8000/api/documents/1/reindex/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
{
  "id": 1,
  "index_status": "indexing"
}
```

#### 1️⃣3️⃣ **DELETE DOCUMENT - Xóa Tài Liệu (Soft Delete)**
```
DELETE http://localhost:8000/api/documents/1/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 204 No Content
```

#### 1️⃣4️⃣ **RESTORE DOCUMENT - Khôi Phục Tài Liệu**
```
POST http://localhost:8000/api/documents/1/restore/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
{
  "id": 1,
  "is_deleted": false
}
```

---

### 💬 CHAT (Hội Thoại)

#### 1️⃣5️⃣ **CREATE CHAT SESSION - Tạo Phiên Chat**
```
POST http://localhost:8000/api/chat/sessions/
Content-Type: application/json

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Body (JSON):
{
  "project": 1,
  "title": "Chat với Tài Liệu",
  "description": "Hỏi đáp về tài liệu"
}

Response: 201 Created
{
  "id": 1,
  "project": 1,
  "title": "Chat với Tài Liệu",
  "message_count": 0,
  "created_at": "2026-05-03T14:40:00Z"
}
```
⚠️ **Save session ID (1 trong ví dụ)**

#### 1️⃣6️⃣ **LIST CHAT SESSIONS - Danh Sách Chat**
```
GET http://localhost:8000/api/chat/sessions/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
[
  {
    "id": 1,
    "title": "Chat với Tài Liệu",
    ...
  }
]
```

#### 1️⃣7️⃣ **GET CHAT SESSION DETAIL - Chi Tiết Chat**
```
GET http://localhost:8000/api/chat/sessions/1/

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
{
  "id": 1,
  "title": "Chat với Tài Liệu",
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "Câu hỏi"
    }
  ]
}
```

#### 1️⃣8️⃣ **SEND MESSAGE - Gửi Tin Nhắn (RAG Question)**
```
POST http://localhost:8000/api/chat/sessions/1/send_message/
Content-Type: application/json

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Body (JSON):
{
  "content": "Tài liệu này nói về cái gì?",
  "selected_document_ids": [1]
}

Response: 200 OK
{
  "message": "Message sent",
  "user_message": {
    "id": 1,
    "role": "user",
    "content": "Tài liệu này nói về cái gì?"
  },
  "assistant_message": {
    "id": 2,
    "role": "assistant",
    "content": "Tài liệu này nói về...",
    "sources": [
      {
        "document_id": 1,
        "title": "Tài Liệu Test",
        "score": 0.95
      }
    ]
  }
}
```

#### 1️⃣9️⃣ **LIST MESSAGES - Danh Sách Tin Nhắn**
```
GET http://localhost:8000/api/chat/messages/?session_id=1

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Response: 200 OK
[
  {
    "id": 1,
    "role": "user",
    "content": "Câu hỏi"
  },
  {
    "id": 2,
    "role": "assistant",
    "content": "Trả lời"
  }
]
```

#### 2️⃣0️⃣ **ADD FEEDBACK - Đánh Giá Câu Trả Lời**
```
POST http://localhost:8000/api/chat/feedback/
Content-Type: application/json

Headers:
Authorization: Bearer <ACCESS_TOKEN>

Body (JSON):
{
  "message": 2,
  "feedback_type": "helpful",
  "comment": "Câu trả lời rất hữu ích"
}

Response: 201 Created
{
  "id": 1,
  "message": 2,
  "feedback_type": "helpful",
  "comment": "Câu trả lời rất hữu ích"
}
```

---

## 📝 HƯỚNG DẪN TỪNG BƯỚC TRONG POSTMAN

### **Bước 1: Tạo Environment Variable để Lưu Token**

1. Click **Environment** ⚙️ (góc trên phải)
2. Click **Create** > tên: `RAG_API`
3. Thêm biến:
   - Tên: `BASE_URL` → Giá trị: `http://localhost:8000/api`
   - Tên: `TOKEN` → Giá trị: (để trống, sẽ điền sau)

### **Bước 2: Đăng Ký & Đăng Nhập**

1. **POST /auth/signup**
   - Method: `POST`
   - URL: `{{BASE_URL}}/auth/signup`
   - Headers: `Content-Type: application/json`
   - Body (JSON):
     ```json
     {
       "email": "testuser@gmail.com",
       "password": "TestPassword123!",
       "password_confirm": "TestPassword123!",
       "first_name": "Test",
       "last_name": "User"
     }
     ```
   - Click **Send**

2. **POST /auth/login**
   - Method: `POST`
   - URL: `{{BASE_URL}}/auth/login`
   - Headers: `Content-Type: application/json`
   - Body (JSON):
     ```json
     {
       "email": "testuser@gmail.com",
       "password": "TestPassword123!"
     }
     ```
   - Click **Send**
   - Copy token từ `response.tokens.access`
   - Chạy script này trong **Tests tab**:
     ```javascript
     var jsonData = pm.response.json();
     pm.environment.set("TOKEN", jsonData.tokens.access);
     ```

### **Bước 3: Tạo Project**

1. **POST /projects/**
   - Method: `POST`
   - URL: `{{BASE_URL}}/projects/`
   - Headers:
     ```
     Authorization: Bearer {{TOKEN}}
     Content-Type: application/json
     ```
   - Body (JSON):
     ```json
     {
       "name": "Dự Án RAG Test",
       "description": "Test project"
     }
     ```
   - Click **Send**
   - Lưu Project ID từ response

### **Bước 4: Tải Lên Tài Liệu**

1. **POST /documents/ (Upload)**
   - Method: `POST`
   - URL: `{{BASE_URL}}/documents/`
   - Headers:
     ```
     Authorization: Bearer {{TOKEN}}
     ```
   - Body: **form-data**
     - project: `1` (ID project vừa tạo)
     - title: `Test Document`
     - file: <chọn file PDF, DOCX, hoặc TXT>
   - Click **Send**
   - Lưu Document ID từ response

### **Bước 5: Tạo Chat Session**

1. **POST /chat/sessions/**
   - Method: `POST`
   - URL: `{{BASE_URL}}/chat/sessions/`
   - Headers:
     ```
     Authorization: Bearer {{TOKEN}}
     Content-Type: application/json
     ```
   - Body (JSON):
     ```json
     {
       "project": 1,
       "title": "Chat Test"
     }
     ```
   - Click **Send**
   - Lưu Session ID từ response

### **Bước 6: Gửi Câu Hỏi (RAG)**

1. **POST /chat/sessions/{id}/send_message/**
   - Method: `POST`
   - URL: `{{BASE_URL}}/chat/sessions/1/send_message/`
   - Headers:
     ```
     Authorization: Bearer {{TOKEN}}
     Content-Type: application/json
     ```
   - Body (JSON):
     ```json
     {
       "content": "Tài liệu này nói về gì?",
       "selected_document_ids": [1]
     }
     ```
   - Click **Send**
   - Nhìn kết quả từ AI

---

## ✅ DANH SÁCH KIỂM TRA (CHECKLIST)

- [ ] Server chạy trên http://localhost:8000
- [ ] Signup thành công
- [ ] Login thành công + lấy token
- [ ] Tạo project thành công
- [ ] Upload tài liệu thành công
- [ ] Tài liệu được index (kiểm tra `index_status`)
- [ ] Tạo chat session thành công
- [ ] Gửi câu hỏi thành công
- [ ] Nhận được câu trả lời từ AI

---

## 🐛 TROUBLESHOOTING

### Lỗi: "Invalid token"
- Kiểm tra token có hết hạn không (60 phút)
- Login lại để lấy token mới

### Lỗi: "Project not found"
- Kiểm tra Project ID có chính xác không
- Kiểm tra project được tạo bởi user hiện tại

### Lỗi: "Unsupported media type"
- Kiểm tra Content-Type headers
- Cho form-data không thêm `Content-Type: application/json`

### Lỗi: "Invalid email domain"
- Chỉ dùng email từ domain thực (gmail.com, hotmail.com)
- Không dùng test.com, example.com

---

## 📚 TÀI LIỆU THÊM

- API Base URL: `http://localhost:8000/api`
- Django Admin: `http://localhost:8000/admin`
- Database: SQLite (db.sqlite3)
- Authentication: JWT Bearer Token

