# 🔍 Backend-Frontend Connection Diagnostic

## Vấn Đề Được Phát Hiện

### 1. **❌ Lỗi Định Dạng Response (CRITICAL)**

**Vị trí**: Frontend `LoginPanel.jsx` dòng 33

```javascript
const errorMessage = err.response?.data?.detail || err.message;
```

**Vấn đề**: Backend không trả về `detail`, mà trả về `serializer.errors`:

```python
# Backend views.py dòng 163
return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
```

**Kết quả**: Frontend nhận được dict lỗi nhưng không hiển thị đúng.

---

### 2. **⚠️ Yêu Cầu Xác Minh Email**

**Vị trí**: Backend `serializers.py` dòng 117-119

```python
if not user.is_email_verified:
    raise serializers.ValidationError('Email not verified. Please check your email.')
```

**Vấn Đề**: Người dùng đăng ký nhưng chưa xác minh email sẽ bị từ chối đăng nhập.

---

### 3. **🔗 Kiểm Tra Kết Nối**

#### Frontend Configuration ✅

- `VITE_API_URL`: `http://localhost:8000/api`
- Interceptor: Tự động thêm `Authorization: Bearer <token>`
- Token refresh: Auto-retry trên 401

#### Backend Configuration ✅

- `ALLOWED_HOSTS`: `localhost,127.0.0.1`
- `CORS_ALLOWED_ORIGINS`: `http://localhost:5173,http://localhost:3000`
- `DEBUG`: `True`
- JWT: Signed with `JWT_SECRET_KEY`

---

## Danh Sách Kiểm Tra - Xác Minh Kết Nối

### Step 1: Kiểm Tra Backend

```bash
cd e:\QLDA_workspace\RAG_BE_QLDA01
python manage.py runserver 0.0.0.0:8000
```

Dấu hiệu thành công:

```
Starting development server at http://127.0.0.1:8000/
```

### Step 2: Kiểm Tra Database

```bash
# Windows PowerShell
python manage.py migrate
python manage.py shell
>>> from apps.auth.models import User
>>> User.objects.all().count()
```

### Step 3: Test Login Endpoint

```bash
# Dùng curl hoặc Postman
POST http://localhost:8000/api/auth/login
Content-Type: application/json

{
  "email": "test@example.com",
  "password": "TestPassword123"
}
```

**Kỳ vọng**: Nếu user không tồn tại:

```json
{
  "email": ["Invalid email or password"],
  "password": ["Invalid email or password"]
}
```

Không phải:

```json
{
  "detail": "..."
}
```

### Step 4: Kiểm Tra Frontend

```bash
cd e:\QLDA_workspace\RAG_FE_QLDA01
npm run dev
```

Truy cập: `http://localhost:5173/`

Mở DevTools (F12) → Console tab → Network tab

---

## Nguyên Nhân Khả Năng Cao

1. **Backend không chạy** → Lỗi CORS / Connection refused
2. **Database chưa migrate** → Table không tồn tại
3. **Email chưa được xác minh** → "Email not verified" error
4. **Mismatch định dạng error** → Frontend không parse được error từ backend
5. **Token không được lưu** → Redirect vẫn về login

---

## Giải Pháp Nhanh

### Fix #1: Chuẩn Hóa Error Response Format

Thêm vào `backend/apps/auth/views.py`:

```python
def format_errors(errors):
    """Convert serializer errors to user-friendly format"""
    if isinstance(errors, dict):
        # Flatten nested errors
        flat_errors = []
        for field, messages in errors.items():
            if isinstance(messages, list):
                flat_errors.extend(messages)
            else:
                flat_errors.append(str(messages))
        return flat_errors[0] if flat_errors else 'Authentication failed'
    return str(errors)

@api_view(['POST'])
@permission_classes([AllowAny])
@ratelimit(key='ip', rate='10/h', method='POST')
def login_view(request):
    serializer = LoginSerializer(data=request.data)

    if serializer.is_valid():
        # ... existing code ...
        return Response({...}, status=status.HTTP_200_OK)

    # Fix: Return consistent error format
    return Response({
        'detail': format_errors(serializer.errors)
    }, status=status.HTTP_401_UNAUTHORIZED)
```

### Fix #2: Frontend Error Handling

Cập nhật `LoginPanel.jsx`:

```javascript
const handleLogin = async (e) => {
  e.preventDefault();
  setError(null);

  if (!email || !password) {
    setError("Please fill in all fields");
    return;
  }

  setLoading(true);
  try {
    const response = await login(email, password);
    authLogin(response.user, response.tokens);
    navigate("/dashboard");
  } catch (err) {
    // Fix: Handle both error formats
    const errorMessage =
      err.response?.data?.detail ||
      err.response?.data?.email?.[0] ||
      err.response?.data?.password?.[0] ||
      err.message ||
      "Login failed";
    setError(errorMessage);
    setAuthError(errorMessage);
  } finally {
    setLoading(false);
  }
};
```

---

## Kiểm Tra Email Verification

Nếu user gặp "Email not verified":

```bash
# Django shell
python manage.py shell
>>> from apps.auth.models import User
>>> user = User.objects.get(email='test@example.com')
>>> user.is_email_verified
False  # ❌

# Fix: Set verified manually (dev only)
>>> user.is_email_verified = True
>>> user.save()

# Hoặc verify token
>>> from apps.auth.models import EmailVerificationToken
>>> token = EmailVerificationToken.objects.get(user=user)
>>> token.mark_as_verified()
```

---

## Test Checklist

- [ ] Backend chạy trên port 8000
- [ ] Database kết nối thành công (`python manage.py migrate`)
- [ ] Có test user: `python manage.py createsuperuser`
- [ ] Frontend chạy trên port 5173
- [ ] Kiểm tra Browser DevTools → Network tab
- [ ] Login request → Status 200 with tokens
- [ ] Tokens lưu vào localStorage
- [ ] Redirect tới /dashboard thành công
- [ ] User info hiển thị ở header/sidebar

---

## Status Codes Reference

| Code       | Meaning                                   |
| ---------- | ----------------------------------------- |
| 200        | ✅ Login success                          |
| 400        | ❌ Invalid input (validation error)       |
| 401        | ❌ Wrong credentials / Email not verified |
| 429        | ❌ Too many login attempts (rate limit)   |
| 500        | ❌ Server error                           |
| CORS error | ❌ Backend không chấp nhận frontend       |

---

**Last Updated**: 2026-05-02
**Priority**: HIGH - Blocking Login Feature
