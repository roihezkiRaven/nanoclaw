FROM python:3.13-slim
RUN pip install --no-cache-dir google-api-python-client==2.200.0 google-auth==2.58.0 google-auth-oauthlib==1.4.1
ENV PYTHONPATH=/lab/tools PYTHONDONTWRITEBYTECODE=1
WORKDIR /lab
