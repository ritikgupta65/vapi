# Deployment Guide

## Overview

This guide covers deploying the Speech-to-Speech AI system to various platforms.

## 📋 Pre-Deployment Checklist

- [ ] All API keys secured in environment variables
- [ ] CORS configured for production domains
- [ ] Error logging implemented
- [ ] Rate limiting added
- [ ] HTTPS/WSS enabled
- [ ] Session management reviewed
- [ ] Testing completed

## 🐳 Docker Deployment

### Create Dockerfiles

**Backend Dockerfile** (`backend/Dockerfile`):
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Frontend Dockerfile** (`frontend/Dockerfile`):
```dockerfile
FROM node:18-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

**Frontend nginx.conf** (`frontend/nginx.conf`):
```nginx
server {
    listen 80;
    server_name _;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    location /session {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### Docker Compose

**docker-compose.yml** (root directory):
```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
      - ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}
      - TTS_PROVIDER=${TTS_PROVIDER:-deepgram}
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
    restart: unless-stopped
```

### Build and Run

```bash
# Create .env file in root directory
cp backend/.env.example .env

# Edit .env with your API keys
nano .env

# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## ☁️ Cloud Deployment Options

### Option 1: AWS (ECS + ALB)

**Architecture:**
- ECS Fargate for backend
- S3 + CloudFront for frontend
- ALB with WebSocket support
- Route53 for DNS

**Steps:**

1. **Build and push Docker images:**
```bash
# Backend
cd backend
docker build -t your-registry/speech-backend:latest .
docker push your-registry/speech-backend:latest

# Frontend (build static files)
cd frontend
npm run build
```

2. **Upload frontend to S3:**
```bash
aws s3 sync dist/ s3://your-bucket-name/
```

3. **Create ECS task definition** (JSON):
```json
{
  "family": "speech-backend",
  "networkMode": "awsvpc",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "your-registry/speech-backend:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        { "name": "OPENAI_API_KEY", "value": "your-key" },
        { "name": "DEEPGRAM_API_KEY", "value": "your-key" }
      ]
    }
  ]
}
```

4. **Configure ALB with WebSocket support**
5. **Update frontend API URL** in environment variables

### Option 2: Google Cloud Platform (Cloud Run)

**Steps:**

1. **Deploy backend:**
```bash
cd backend

# Build and deploy
gcloud run deploy speech-backend \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY=your-key,DEEPGRAM_API_KEY=your-key
```

2. **Deploy frontend to Firebase Hosting:**
```bash
cd frontend
npm run build

firebase init hosting
firebase deploy
```

### Option 3: Azure (Container Apps)

**Steps:**

1. **Create Container Registry:**
```bash
az acr create --resource-group myResourceGroup \
  --name myregistry --sku Basic
```

2. **Build and push:**
```bash
cd backend
az acr build --registry myregistry \
  --image speech-backend:latest .
```

3. **Deploy Container App:**
```bash
az containerapp create \
  --name speech-backend \
  --resource-group myResourceGroup \
  --image myregistry.azurecr.io/speech-backend:latest \
  --environment myEnvironment \
  --ingress external \
  --target-port 8000 \
  --env-vars \
    OPENAI_API_KEY=your-key \
    DEEPGRAM_API_KEY=your-key
```

### Option 4: DigitalOcean (App Platform)

**Steps:**

1. Push code to GitHub
2. Connect DigitalOcean App Platform to your repo
3. Configure environment variables in dashboard
4. Deploy with one click

### Option 5: Heroku

**Backend (heroku.yml):**
```yaml
build:
  docker:
    web: backend/Dockerfile
run:
  web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Deploy:**
```bash
heroku create speech-backend
heroku config:set OPENAI_API_KEY=your-key
heroku config:set DEEPGRAM_API_KEY=your-key
git push heroku main
```

## 🔒 Security Hardening

### 1. Environment Variables

**Never commit .env files!**

Use secrets management:
- AWS: Secrets Manager or Parameter Store
- GCP: Secret Manager
- Azure: Key Vault
- Docker: Secrets
- Kubernetes: Secrets

### 2. Update CORS

In `backend/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://yourdomain.com",
        "https://www.yourdomain.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3. Add Rate Limiting

Install: `pip install slowapi`

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

@app.post("/session")
@limiter.limit("10/minute")
async def create_session(request: Request, ...):
    ...
```

### 4. Add Authentication

Example with JWT:

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=["HS256"]
        )
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

@app.post("/session")
async def create_session(
    request: SessionCreate,
    user = Depends(verify_token)
):
    ...
```

### 5. HTTPS/WSS Only

**Let's Encrypt with Nginx:**
```bash
sudo certbot --nginx -d yourdomain.com
```

**In production, reject HTTP:**
```python
if not request.url.scheme.startswith("https"):
    raise HTTPException(status_code=403, detail="HTTPS required")
```

## 📊 Monitoring

### Application Monitoring

**Add Prometheus metrics:**
```bash
pip install prometheus-fastapi-instrumentator
```

```python
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
```

**Custom metrics:**
```python
from prometheus_client import Counter, Histogram

session_counter = Counter('sessions_created_total', 'Total sessions created')
stt_latency = Histogram('stt_latency_seconds', 'STT latency')

@app.post("/session")
async def create_session(...):
    session_counter.inc()
    ...
```

### Logging

**Add structured logging:**
```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
        }
        return json.dumps(log_obj)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.getLogger().addHandler(handler)
```

### Error Tracking

**Sentry integration:**
```bash
pip install sentry-sdk
```

```python
import sentry_sdk

sentry_sdk.init(
    dsn="your-sentry-dsn",
    traces_sample_rate=1.0,
)
```

## 🔄 CI/CD Pipeline

### GitHub Actions Example

**.github/workflows/deploy.yml:**
```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v2
      
      - name: Build backend
        run: |
          cd backend
          docker build -t speech-backend .
      
      - name: Build frontend
        run: |
          cd frontend
          npm ci
          npm run build
      
      - name: Deploy to production
        env:
          DEPLOY_KEY: ${{ secrets.DEPLOY_KEY }}
        run: |
          # Your deployment commands here
```

## 🧪 Production Testing

### Load Testing

**Using Locust:**
```python
from locust import HttpUser, task, between

class SpeechUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def create_session(self):
        self.client.post("/session", json={
            "system_prompt": "Test prompt"
        })
```

### WebSocket Testing

```python
import asyncio
import websockets

async def test_websocket():
    uri = "ws://localhost:8000/session/test-id/audio/in"
    async with websockets.connect(uri) as ws:
        await ws.send(b'\x00' * 1024)
        
asyncio.run(test_websocket())
```

## 📈 Scaling Strategies

### Horizontal Scaling

1. **Stateless backend** - no in-memory session storage
2. **Redis** for session management
3. **Load balancer** with sticky sessions
4. **Message queue** for async processing

### Caching

```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

@app.on_event("startup")
async def startup():
    redis = aioredis.from_url("redis://localhost")
    FastAPICache.init(RedisBackend(redis), prefix="cache:")
```

### Database for Sessions

```python
# Use PostgreSQL or MongoDB for persistent sessions
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db")
```

## 🚨 Troubleshooting Production

### Common Issues

**WebSocket disconnections:**
- Check load balancer timeout settings
- Implement ping/pong heartbeat
- Add reconnection logic in frontend

**High latency:**
- Use CDN for frontend assets
- Deploy closer to users (multi-region)
- Optimize API calls

**Memory leaks:**
- Monitor memory usage
- Implement session cleanup
- Use connection pooling

### Health Checks

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "stt": check_deepgram_connection(),
            "llm": check_openai_connection(),
            "tts": check_tts_connection()
        }
    }
```

---

## Summary

1. ✅ Use Docker for consistent deployments
2. ✅ Choose cloud provider based on needs
3. ✅ Implement security best practices
4. ✅ Add monitoring and logging
5. ✅ Test thoroughly before production
6. ✅ Plan for horizontal scaling
7. ✅ Monitor costs (API usage!)

**Cost Considerations:**
- Deepgram: ~$0.0045/min
- OpenAI: ~$0.40/1M tokens
- ElevenLabs: ~$0.30/1K chars
- Server: $5-50/month depending on traffic

**Recommended starter setup:**
- DigitalOcean App Platform ($12/month)
- Or AWS Free Tier (first year)
- Scale up as needed
