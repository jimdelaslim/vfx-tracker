const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');

function installPythonDeps(resourcesPath, callback) {
    const requirementsPath = path.join(resourcesPath, 'requirements.txt');
    
    if (!fs.existsSync(requirementsPath)) {
        console.log('No requirements.txt found');
        return callback(null);
    }
    
    console.log('Installing Python dependencies...');
    exec(`/usr/bin/python3 -m pip install --user -r "${requirementsPath}"`, (error, stdout, stderr) => {
        if (error) {
            console.error('Error installing dependencies:', error);
            return callback(error);
        }
        console.log('Dependencies installed successfully');
        callback(null);
    });
}

module.exports = { installPythonDeps };
