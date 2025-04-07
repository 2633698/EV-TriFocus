import os
import shutil
import sys

def create_directory_structure():
    """Create the necessary directory structure for the EV charging simulation system."""
    # Base directories
    directories = [
        'static',
        'static/css',
        'static/js',
        'static/images',
        'templates',
        'output',
        'models'
    ]
    
    # Create directories
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"Created directory: {directory}")
    
    # Create configuration file if it doesn't exist
    if not os.path.exists('config.json'):
        # Config file should be created by the app.py script
        print("Note: config.json will be created when running app.py")
    
    print("Directory structure setup complete!")

def check_python_files():
    """Check if the required Python files exist."""
    required_files = [
        'app.py',
        'ev_charging_scheduler.py',
        'ev_integration_scheduler.py',
        'ev_model_training.py',
        'ev_multi_agent_system.py',
        'ev_system_test.py',
        'ev_main.py'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("Warning: Some required Python files are missing:")
        for file in missing_files:
            print(f" - {file}")
        print("Please make sure these files are present before running the application.")
    else:
        print("All required Python files are present.")

def copy_frontend_files():
    """Copy frontend files to the appropriate directories."""
    # Templates
    template_files = {
        'index.html': 'templates/index.html',
        'user.html': 'templates/user.html',
        'operator.html': 'templates/operator.html',
        'grid.html': 'templates/grid.html'
    }
    
    # JavaScript files
    js_files = {
        'main.js': 'static/js/main.js',
        'user.js': 'static/js/user.js',
        'operator.js': 'static/js/operator.js',
        'grid.js': 'static/js/grid.js'
    }
    
    # CSS files
    css_files = {
        'style.css': 'static/css/style.css'
    }
    
    # Copy template files
    for source, dest in template_files.items():
        if os.path.exists(source):
            shutil.copy2(source, dest)
            print(f"Copied {source} to {dest}")
        else:
            print(f"Warning: {source} does not exist. Skipping...")
    
    # Copy JavaScript files
    for source, dest in js_files.items():
        if os.path.exists(source):
            shutil.copy2(source, dest)
            print(f"Copied {source} to {dest}")
        else:
            print(f"Warning: {source} does not exist. Skipping...")
    
    # Copy CSS files
    for source, dest in css_files.items():
        if os.path.exists(source):
            shutil.copy2(source, dest)
            print(f"Copied {source} to {dest}")
        else:
            print(f"Warning: {source} does not exist. Skipping...")

def main():
    print("Setting up EV Charging Simulation System...")
    create_directory_structure()
    check_python_files()
    
    # Ask if user wants to copy frontend files
    if '--copy' in sys.argv:
        copy_frontend_files()
    else:
        print("\nTo copy frontend files to the appropriate directories, run:")
        print("python setup.py --copy")
    
    print("\nSetup complete. To run the application:")
    print("1. Make sure all required files are present")
    print("2. Run 'python app.py' to start the Flask server")
    print("3. Access the application at http://localhost:5000")

if __name__ == "__main__":
    main()
