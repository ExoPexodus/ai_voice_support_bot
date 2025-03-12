import os
import csv
import requests

# Configurable CSV file path for job data (set this in your .env file)
CSV_JOB_DATA_PATH = os.getenv("JOB_DATA_CSV", "src/data/jobs.csv")
JOB_API_ENDPOINT = os.getenv("JOB_API_ENDPOINT", "https://api.example.com/jobs")

def fetch_job_postings(role, location, source="csv"):
    """
    Fetch job postings based on the candidate's desired role or location.
    If both are empty, return all job data.
    """
    if source == "csv":
        return fetch_jobs_from_csv(role, location)
    elif source == "api":
        return fetch_jobs_from_api(role, location)
    else:
        return {"error": "Invalid data source specified"}

def fetch_jobs_from_csv(role, location):
    """
    Reads job postings from a CSV file. If role and location are provided,
    filters accordingly; otherwise, returns all rows.
    """
    try:
        with open(CSV_JOB_DATA_PATH, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            jobs = []
            for row in reader:
                # If both role and location are empty, include every row.
                if not role and not location:
                    jobs.append(row)
                else:
                    job_title = row.get("job_title", "").lower()
                    job_location = row.get("location", "").lower()
                    
                    role_match = role.lower() in job_title if role else False
                    location_match = location.lower() in job_location if location else False
                    
                    # Include the job if either condition is met.
                    if role_match or location_match:
                        jobs.append(row)
            return jobs if jobs else {"error": "No jobs found matching the specified criteria"}
    except Exception as e:
        return {"error": f"Error reading CSV: {str(e)}"}

def fetch_jobs_from_api(role, location):
    """
    Calls an external API to fetch job postings based on the role and location.
    """
    try:
        response = requests.get(f"{JOB_API_ENDPOINT}?role={role}&location={location}")
        if response.status_code == 200:
            return response.json()
        return {"error": f"API request failed with status code {response.status_code}"}
    except Exception as e:
        return {"error": f"API request error: {str(e)}"}

if __name__ == "__main__":
    # Example usage:
    # To fetch all job data, pass empty strings for both role and location.
    print("All job data (unfiltered):")
    print(fetch_job_postings("", "", source="csv"))
    
    # Filtered examples:
    print("Filtered job data for 'engineer' in 'Bangalore':")
    print(fetch_job_postings("engineer", "Bangalore", source="csv"))
    print("Filtered job data for 'designer' in 'Mumbai' using API:")
    print(fetch_job_postings("designer", "Mumbai", source="api"))
