FROM apify/actor-python:3.12

# Copy requirements.txt first
COPY --chown=myuser:myuser requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code into container
COPY --chown=myuser:myuser . ./

# Run the Standby Actor web server
CMD ["python3", "main.py"]
