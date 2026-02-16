# Auth & Session Management

A secure authentication system for the Mansa ecosystem, utilizing **JSON Web Tokens (JWT)** and **HttpOnly Cookies** to manage user sessions and access levels. This module ensures that user data is protected against common attacks like XSS by restricting token access to the server-side.

Built to integrate seamlessly with the main database and provide granular permission control across all Mansa services.

## Usage
1. Environment configuration (`.env`):
   ```env
    #
    #$ DATABASE CONFIGURATION
    #
    MYSQL_USER=user
    MYSQL_PASSWORD=password
    MYSQL_HOST=localhost
    MYSQL_DATABASE=database

    #
    #$ AUTH SYSTEM
    #
    AUTH_ENABLED=TRUE
    AUTH_HOST=localhost
    AUTH_PORT=3200
    
    # Secret key for JWT signing
    JEW_TOKEN=your_super_secret_jwt_key

    # Google OAuth2
    GOOGLE_CLIENT.ID=your_id
    GOOGLE_CLIENT.SECRET=your_secret
    GOOGLE_REDIRECT.URI=http://localhost:3200/auth/callback
   ```

## Access Levels
The system uses a bit-flag style (or specific integer) level system to control permissions:

| Level | Name | Description |
| :--- | :--- | :--- |
| **00** | Free | Standard access to public data. |
| **01** | Developer | Access to generate and use API Keys. |
| **10** | Premium | Enhanced quotas and exclusive features. |
| **11** | Premium Developer | Combined benefits of both levels. |
| **67** | Admin | Full control over the system and user management. |

## API Endpoints

### Health Check
```bash
curl http://localhost:3200/auth/health
```
Returns service status.

### User Registration
Creates a new account with default access level `00`.
```bash
curl -X POST "http://localhost:3200/auth/register" \
     -H "Content-Type: application/json" \
     -d '{"username": "user", "email": "user@example.com", "password": "password123"}'
```

### User Login
Authenticates the user and initiates a session.
```bash
curl -X POST "http://localhost:3200/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"username": "user", "password": "password123"}'
```
**Response Behavior:**
- Sets a `mansa_token` cookie (HttpOnly, Secure, SameSite=Lax).
- Returns a JSON object with `accessToken` (for manual header use) and user metadata.

### Profile (Me)
Retrieves the logged-in user's information. Requires a valid session cookie or Authorization header.
```bash
curl -X GET "http://localhost:3200/auth/me" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

### Google OAuth2 Login
Initiates the Google authentication flow.
```bash
# Redirect your browser to:
GET http://localhost:3200/auth/google
```

### Google Callback
Internal endpoint handled by the server. After successful Google login, it:
1. Verifies the user with Google.
2. Synchronizes the user with the local MySQL database.
3. Redirects to the frontend with the token in the URL fragment:
   `http://127.0.0.1:5500/main/test/auth.html#token=ACCESS_TOKEN`

## Security Features

- **Bcrypt Hashing**: All passwords are salted and hashed using the Blowfish algorithm (bcrypt).
- **Auto-increment Gap Prevention**: The registration flow performs pre-insertion checks for existing usernames/emails to prevent database ID gaps on failed attempts.
- **Stateless Authentication**: JWT allows the server to verify users without session storage.
- **CORS Protection**: Configured with dynamic origin matching to allow authenticated requests from trusted frontends while maintaining security.

## Workflow

```mermaid
graph TD
    User["User Interface"] --> Start{Login Method?}
    
    Start -- Standard --> Login["POST /auth/login"]
    Login --> Verify["Verify Bcrypt Hash"]
    Verify -- Success --> JWT["Generate JWT"]
    
    Start -- Google --> GLogin["GET /auth/google"]
    GLogin --> GRedirect["Redirect to Google"]
    GRedirect --> GCallback["GET /auth/callback"]
    GCallback --> GVerify["Verify Google Token"]
    GVerify --> GSync["Sync User in MySQL"]
    GSync --> JWT
    
    Start -- Register --> Reg["POST /auth/register"]
    Reg --> Valid["Check Duplicate User"]
    Valid -- OK --> Hash["Hash Password"]
    Hash --> Save["Save to MySQL"]
    Save --> JWT
    
    JWT --> Cookie["Set Cookie & Redirect"]
    Cookie --> Home["Access Granted"]
```

## License
Mansa Team's MODIFIED GPL 3.0 License. See LICENSE for details.
