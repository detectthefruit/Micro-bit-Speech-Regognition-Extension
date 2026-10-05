import os
import time
import zipfile
import subprocess
import requests

# --- CONFIGURATION ---
API_KEY = "ei_2509694b678d5fdd89d70f70acadde9620bf3c873d21699e"  # Your Edge Impulse Studio API Key
PROJECT_ID = "1129254"    # Your Edge Impulse Project ID
OUTPUT_DIR = "./microbit-build"
HEX_OUTPUT_PATH = "./MICROBIT.hex"

HEADERS = {
    "x-api-key": API_KEY,
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def trigger_c_library_deployment():
    """Tells Edge Impulse to compile and prepare the C++ library export."""
    print("Step 1: Requesting C++ library build from Edge Impulse...")
    url = f"https://edgeimpulse.com{PROJECT_ID}/deployment"
    
    # We use 'zip' format to fetch the raw C++ deployment pack
    payload = {
        "engine": "tflite-eon", # Uses the optimized EON compiler for memory efficiency
        "modelType": "int8",     # int8 quantization is required for micro:bit memory constraints
        "format": "zip"
    }
    
    response = requests.post(url, json=payload, headers=HEADERS)
    if response.status_code != 200:
        raise Exception(f"Failed to start deployment: {response.text}")
        
    job_id = response.json().get("id")
    print(f"Deployment job started with ID: {job_id}")
    return job_id

def monitor_job(job_id):
    """Polls the API until the library build is finished."""
    print("Step 2: Monitoring build status...")
    url = f"https://edgeimpulse.com{PROJECT_ID}/jobs/{job_id}/status"
    
    while True:
        response = requests.get(url, headers=HEADERS)
        status = response.json().get("job", {}).get("status")
        
        if status == "finished":
            print("Edge Impulse build complete!")
            break
        elif status == "failed":
            raise Exception("Edge Impulse compilation failed on the server side.")
        
        print("Still compiling... waiting 5 seconds.")
        time.sleep(5)

def download_and_extract_library():
    """Downloads the compiled C++ zip bundle and extracts it to the project directory."""
    print("Step 3: Downloading C++ deployment bundle...")
    url = f"https://edgeimpulse.com{PROJECT_ID}/deployment/download?format=zip"
    
    response = requests.get(url, headers=HEADERS, stream=True)
    zip_path = os.path.join(OUTPUT_DIR, "model.zip")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            
    print("Extracting files...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # Puts edge-impulse-sdk, model-parameters, and tflite-model folders into place
        zip_ref.extractall(os.path.join(OUTPUT_DIR, "source")) 
    
    os.remove(zip_path)

def build_hex_via_docker():
    """Clones the official voice-activated microbit repo wrapper and compiles using Docker."""
    print("Step 4: Cloning voice-activated-microbit build wrapper...")
    repo_dir = "./voice-activated-microbit"
    
    if not os.path.exists(repo_dir):
        subprocess.run(["git", "clone", "https://github.com", repo_dir], check=True)
    
    # Move the freshly downloaded edge impulse source model code into the wrapper's build tree
    print("Syncing model files into micro:bit firmware source...")
    subprocess.run(f"cp -r {OUTPUT_DIR}/source/* {repo_dir}/source/", shell=True, check=True)
    
    print("Step 5: Invoking Docker toolchain container to build .hex file...")
    # Step A: Build the toolchain container layout locally
    subprocess.run(["docker", "build", "-t", "microbit_ei_build", repo_dir], check=True)
    
    # Step B: Spin up container to execute build scripts and output the HEX file
    abs_repo_path = os.path.abspath(repo_dir)
    subprocess.run([
        "docker", "run", "--rm", 
        "-v", f"{abs_repo_path}:/app", 
        "microbit_ei_build"
    ], check=True)
    
    generated_hex = os.path.join(repo_dir, "MICROBIT.hex")
    if os.path.exists(generated_hex):
        subprocess.run(["cp", generated_hex, HEX_OUTPUT_PATH], check=True)
        print(f"\n Success! Final binary generated at: {os.path.abspath(HEX_OUTPUT_PATH)}")
    else:
        print("Compilation finished, but MICROBIT.hex was not found in the output workspace.")

if __name__ == "__main__":
    try:
        job_id = trigger_c_library_deployment()
        monitor_job(job_id)
        download_and_extract_library()
        build_hex_via_docker()
    except Exception as e:
        print(f"\n[ERROR] Build pipeline interrupted: {e}")