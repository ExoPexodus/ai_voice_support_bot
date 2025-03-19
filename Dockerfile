FROM python:3.10.12-slim

# Set the working directory
WORKDIR /app

RUN apt install ffmpeg
# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire codebase
COPY . .

# Expose the FastAGI port so that Asterisk (or other callers) can connect
EXPOSE 4577

# Set the container's entrypoint to run the FastAGI server
CMD ["python", "fastagi_server.py"]
