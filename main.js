const { app, BrowserWindow, Menu, dialog, ipcMain } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const kill = require('tree-kill');
const fs = require('fs');

// Recent projects management
const MAX_RECENT_PROJECTS = 10;
let recentProjects = [];
const recentProjectsFile = path.join(app.getPath('userData'), 'recent-projects.json');

let mainWindow;
let flaskProcess;
let currentProjectPath = null;

// Start Flask server with virtual environment
function startFlask() {
    // Detect if running as packaged app
    const isPackaged = app.isPackaged;
    const isWin = process.platform === 'win32';
    
    // Use bundled venv in both packaged and dev mode
    let pythonPath, appDir;
    if (isPackaged) {
        appDir = process.resourcesPath;
        if (isWin) {
            pythonPath = path.join(appDir, 'vfx-server.exe');
        } else {
            const venvPath = path.join(appDir, 'venv');
            pythonPath = path.join(venvPath, 'bin', 'python3');
        }
    } else {
        const venvPath = path.join(__dirname, 'venv');
        pythonPath = isWin 
            ? path.join(venvPath, 'Scripts', 'python.exe')
            : path.join(venvPath, 'bin', 'python3');
        appDir = __dirname;
    }
    
    console.log('Starting Flask...');
    console.log('  isPackaged:', isPackaged);
    console.log('  pythonPath:', pythonPath);
    console.log('  appDir:', appDir);
    
    // Pass current database path to Flask
    const env = { 
        ...process.env, 
        FLASK_ENV: 'production',
        PYTHONPATH: appDir
    };
    if (process.env.VFX_DB_PATH) {
        env.VFX_DB_PATH = process.env.VFX_DB_PATH;
        console.log('  database:', env.VFX_DB_PATH);
    }
    
    // Show spawn info in dialog for debugging
    const spawnInfo = `Python: ${pythonPath}
Working dir: ${appDir}
Packaged: ${app.isPackaged}`;
    
    // Safety: On Windows, kill any existing process on port 5001 before starting
    if (process.platform === 'win32') {
        try {
            const { execSync } = require('child_process');
            const result = execSync('netstat -ano | findstr :5001 | findstr LISTENING', { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] });
            const lines = result.trim().split('\n');
            for (const line of lines) {
                const parts = line.trim().split(/\s+/);
                const oldPid = parts[parts.length - 1];
                if (oldPid && !isNaN(oldPid)) {
                    console.log('Killing orphan Flask on port 5001 (PID: ' + oldPid + ')');
                    try { execSync('taskkill /PID ' + oldPid + ' /T /F', { stdio: 'ignore' }); } catch(e) {}
                }
            }
        } catch (e) {
            // No process on port 5001, good
        }
    }

    try {
        const spawnArgs = (app.isPackaged && process.platform === 'win32') ? [] : ['app.py'];
        flaskProcess = spawn(pythonPath, spawnArgs, {
            cwd: appDir,
            env: env
        });

        
    } catch (error) {
        dialog.showErrorBox('Spawn Error', `Could not start Python:

${error.message}

${spawnInfo}`);
        return;
    }

    flaskProcess.stdout.on('data', (data) => {
        console.log(`Flask: ${data}`);
    });

    flaskProcess.stderr.on('data', (data) => {
        console.error(`Flask Error: ${data}`);
    });
    
    flaskProcess.on('error', (error) => {
        console.error('Failed to start Flask:', error);
    });
}

// Stop Flask server
function stopFlask() {
    if (flaskProcess && flaskProcess.pid) {
        const pid = flaskProcess.pid;
        console.log('Killing Flask (PID:', pid, ')');
        
        const isWin = process.platform === 'win32';
        
        try {
            if (isWin) {
                // Windows: use taskkill to force kill the process tree
                const { execSync } = require('child_process');
                try {
                    execSync('taskkill /PID ' + pid + ' /T /F', { stdio: 'ignore' });
                    console.log('Flask killed via taskkill');
                } catch (e) {
                    console.log('taskkill finished (process may already be stopped)');
                }
            } else {
                // macOS/Linux: SIGKILL
                process.kill(pid, 'SIGKILL');
                console.log('Flask killed');
            }
        } catch (error) {
            console.error('Error killing Flask:', error);
        }
        
        flaskProcess = null;
    }
}

// Show project picker dialog
function showProjectPicker() {
    const { BrowserWindow } = require('electron');
    
    // Create a small picker window
    const pickerWindow = new BrowserWindow({
        width: 500,
        height: 400,
        resizable: false,
        minimizable: false,
        maximizable: false,
        center: true,
        title: 'VFX Shot Tracker',
        icon: path.join(__dirname, 'icon.icns'),
    webPreferences: {
            nodeIntegration: true,
            contextIsolation: false
        }
    });
    
    // Build HTML with inline JavaScript
    const pickerHTML = `
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    padding: 20px;
                    background: #f5f5f5;
                    overflow-y: auto;
                    height: 100vh;
                }
                .container {
                    max-width: 460px;
                    margin: 0 auto;
                }
                .button {
                    display: block;
                    width: 100%;
                    padding: 15px;
                    margin: 10px 0;
                    border: 2px solid #20b2aa;
                    border-radius: 8px;
                    background: white;
                    cursor: pointer;
                    text-align: left;
                    font-size: 14px;
                    transition: all 0.2s;
                    text-decoration: none;
                    color: #333;
                }
                .button:hover {
                    background: #20b2aa;
                    color: white;
                }
                .button:hover .project-path {
                    color: rgba(255, 255, 255, 0.8);
                }
                .button.new-project {
                    background: #20b2aa;
                    color: white;
                    font-weight: bold;
                    text-align: center;
                }
                .button.new-project:hover {
                    background: #1a9d96;
                }
                .recent-label {
                    margin-top: 20px;
                    margin-bottom: 10px;
                    color: #666;
                    font-size: 12px;
                    text-transform: uppercase;
                    font-weight: 600;
                }
                .project-name {
                    font-weight: 500;
                    color: inherit;
                }
                .project-path {
                    font-size: 11px;
                    color: #999;
                    margin-top: 4px;
                }
                .no-recent {
                    text-align: center;
                    color: #999;
                    padding: 20px;
                    font-style: italic;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="button new-project" onclick="selectAction('new-project')">
                    + New Project
                </div>
                <div class="button" style="text-align: center;" onclick="selectAction('open-project')">
                    Open Existing Project...
                </div>
                
                ${recentProjects.length > 0 ? `
                    <div class="recent-label">Recent Projects</div>
                    ${recentProjects.map((proj, idx) => `
                        <div class="button" onclick="selectAction('recent-${idx}')">
                            <div class="project-name">${path.basename(proj)}</div>
                            <div class="project-path">${proj}</div>
                        </div>
                    `).join('')}
                ` : '<div class="no-recent">No recent projects</div>'}
            </div>
            
            <script>
                const { ipcRenderer } = require('electron');
                
                function selectAction(action) {
                    console.log('Selected:', action);
                    ipcRenderer.send('picker-action', action);
                }
            </script>
        </body>
        </html>
    `;
    
    pickerWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(pickerHTML));
    
    pickerWindow.on('closed', () => {
        // Don't auto-quit when picker closes
        // If user cancels dialogs, we'll show picker again
        console.log('Picker window closed');
    });
}

// Check if Flask is responding
async function waitForFlask(maxAttempts = 30) {
    for (let i = 0; i < maxAttempts; i++) {
        try {
            const response = await fetch('http://localhost:5001/');
            if (response.ok) {
                console.log('✓ Flask is ready!');
                return true;
            }
        } catch (error) {
            // Flask not ready yet
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
        console.log(`Waiting for Flask... (${i + 1}/${maxAttempts})`);
    }
    console.error('✗ Flask failed to start');
    return false;
}

// Create main window
function createWindow() {
    if (mainWindow) {
        console.log('Main window already exists');
        mainWindow.show();
        return;
    }
    
    console.log('Creating main window...');
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        icon: path.join(__dirname, 'icon.icns'),
    webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
            enableWebSQL: false,
            enableBlinkFeatures: '',
            // Allow clipboard access
            sandbox: false
        },
        title: 'VFX Shot Tracker',
        show: false // Don't show until ready
    });

    // Load URL immediately since Flask is already running
    mainWindow.loadURL('http://localhost:5001');
    
    // Show when ready
    mainWindow.once('ready-to-show', () => {
        console.log('Main window ready to show');
        mainWindow.show();
        // Update title after page loads
        setTimeout(() => {
            updateWindowTitle();
        }, 100);
    });

    mainWindow.on('closed', () => {
        console.log('Main window closed');
        mainWindow = null;
    });
}

// File Menu Actions
function newProject() {
    dialog.showSaveDialog(mainWindow, {
        title: 'Create New Project',
        defaultPath: 'untitled_project.db',
        filters: [{ name: 'VFX Tracker Project', extensions: ['db'] }]
    }).then(result => {
        if (!result.canceled) {
            currentProjectPath = result.filePath;
            // Create new database at this path
            setDatabasePath(currentProjectPath);
            updateWindowTitle();
            addToRecentProjects(currentProjectPath);
        } else if (!mainWindow) {
            // If cancelled and no main window exists, show picker again
            showProjectPicker();
        }
    });
}

// Helper function to open a database file with validation
function openDatabaseFile(filePath) {
    return new Promise((resolve) => {
        if (filePath) {
            // File path provided, validate and open
            if (!fs.existsSync(filePath)) {
                dialog.showErrorBox('File Not Found', `Could not find file: ${filePath}`);
                resolve(false);
                return;
            }
            
            currentProjectPath = filePath;
            updateWindowTitle();
            setTimeout(() => {
                setDatabasePath(filePath);
                addToRecentProjects(filePath);
            }, 500);
            resolve(true);
        } else {
            // Show open dialog
            dialog.showOpenDialog(null, {
                title: 'Open Project',
                filters: [
                    { name: 'VFX Tracker Project', extensions: ['db'] },
                    { name: 'All Files', extensions: ['*'] }
                ],
                properties: ['openFile']
            }).then(result => {
                if (!result.canceled && result.filePaths.length > 0) {
                    const selectedPath = result.filePaths[0];
                    
                    if (!fs.existsSync(selectedPath)) {
                        dialog.showErrorBox('File Not Found', `Could not find file: ${selectedPath}`);
                        resolve(false);
                        return;
                    }
                    
                    currentProjectPath = selectedPath;
                    updateWindowTitle();
                    setTimeout(() => {
                        setDatabasePath(selectedPath);
                        addToRecentProjects(selectedPath);
                    }, 500);
                    resolve(true);
                } else {
                    resolve(false);
                }
            });
        }
    });
}

function openProject() {
    openDatabaseFile(null).then(success => {
        if (!success && !mainWindow) {
            // If cancelled and no main window exists, show picker again
            showProjectPicker();
        }
    });
}

function saveProject() {
    if (!currentProjectPath) {
        saveProjectAs();
    } else {
        // Projects auto-save, no action needed
        console.log('Project is already saved at:', currentProjectPath);
    }
}

function saveProjectAs() {
    dialog.showSaveDialog(mainWindow, {
        title: 'Save Project As',
        defaultPath: currentProjectPath || 'untitled_project.db',
        filters: [{ name: 'VFX Tracker Project', extensions: ['db'] }]
    }).then(result => {
        if (!result.canceled) {
            const newPath = result.filePath;
            
            // Copy current database file to new location
            const fs = require('fs');
            
            // Get current database path from Flask
            fetch('http://localhost:5001/api/get_database_path')
                .then(response => response.json())
                .then(data => {
                    const currentDbPath = data.path;
                    console.log(`Copying ${currentDbPath} to ${newPath}`);
                    
                    // Copy the file
                    fs.copyFileSync(currentDbPath, newPath);
                    
                    // Now switch to the new copy
                    currentProjectPath = newPath;
                    setDatabasePath(newPath);
                    updateWindowTitle();
                    
                    dialog.showMessageBox(mainWindow, {
                        type: 'info',
                        title: 'Project Saved',
                        message: `Project copied to ${path.basename(newPath)}`,
                        buttons: ['OK']
                    });
                })
                .catch(error => {
                    console.error('Error copying database:', error);
                    dialog.showErrorBox('Save Error', `Failed to copy project: ${error.message}`);
                });
        }
    });
}

function updateWindowTitle() {
    console.log('updateWindowTitle called:', {
        hasWindow: !!mainWindow,
        hasPath: !!currentProjectPath,
        path: currentProjectPath
    });
    
    if (mainWindow && currentProjectPath) {
        const filename = path.basename(currentProjectPath);
        mainWindow.setTitle(`VFX Shot Tracker - ${filename}`);
        console.log('✓ Window title set to:', filename);
    } else if (mainWindow) {
        mainWindow.setTitle('VFX Shot Tracker');
        console.log('✓ Window title set to default');
    } else {
        console.log('✗ Cannot set title - no window exists yet');
    }
}


// Set database path via Flask API
function setDatabasePath(dbPath) {
    console.log('Switching database to:', dbPath);
    
    // Set environment variable for Flask to use
    process.env.VFX_DB_PATH = dbPath;
    
    fetch('http://localhost:5001/api/set_database_path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: dbPath })
    })
    .then(response => {
        console.log('Response status:', response.status);
        if (!response.ok) {
            return response.json().then(err => {
                throw new Error(err.error || 'Unknown error');
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Database switched successfully:', data);
        
        // Restart Flask to pick up new database
        console.log('Restarting Flask server...');
        stopFlask();
        
        setTimeout(() => {
            startFlask();
            waitForFlask().then(ready => {
                if (ready && mainWindow) {
                    mainWindow.reload();
                }
            });
        }, 500);
    })
    .catch(error => {
        console.error('Error switching database:', error);
        
        // Show more helpful error message
        let errorMsg = 'Failed to switch database.\n\n';
        
        if (error.message.includes('Invalid database file')) {
            errorMsg += 'This file is not a valid SQLite database.';
        } else if (error.message.includes('ENOENT')) {
            errorMsg += 'The database file could not be found.';
        } else if (error.message.includes('EACCES')) {
            errorMsg += 'Permission denied. Check file permissions.';
        } else if (error.message.includes('database is locked')) {
            errorMsg += 'Database is locked. Make sure it\'s not open in another application.';
        } else {
            errorMsg += `Error: ${error.message}`;
        }
        
        dialog.showMessageBox(mainWindow, {
            type: 'error',
            title: 'Database Error',
            message: errorMsg,
            buttons: ['OK']
        });
    });
}

// Load recent projects from disk
function loadRecentProjects() {
    try {
        if (fs.existsSync(recentProjectsFile)) {
            const data = fs.readFileSync(recentProjectsFile, 'utf8');
            recentProjects = JSON.parse(data);
            console.log('Loaded recent projects:', recentProjects);
        }
    } catch (error) {
        console.error('Error loading recent projects:', error);
        recentProjects = [];
    }
}

// Save recent projects to disk
function saveRecentProjects() {
    try {
        fs.writeFileSync(recentProjectsFile, JSON.stringify(recentProjects, null, 2));
        console.log('Saved recent projects');
    } catch (error) {
        console.error('Error saving recent projects:', error);
    }
}

// Add project to recent list
function addToRecentProjects(projectPath) {
    // Remove if already exists
    recentProjects = recentProjects.filter(p => p !== projectPath);
    
    // Add to front
    recentProjects.unshift(projectPath);
    
    // Keep only MAX_RECENT_PROJECTS
    recentProjects = recentProjects.slice(0, MAX_RECENT_PROJECTS);
    
    // Save to disk
    saveRecentProjects();
    
    // Rebuild menu to show updated list
    createMenu();
}

// Remove project from recent list (if file not found)
function removeFromRecentProjects(projectPath) {
    recentProjects = recentProjects.filter(p => p !== projectPath);
    saveRecentProjects();
    createMenu();
}

// Open a recent project
function openRecentProject(projectPath) {
    // Check if file exists
    if (!fs.existsSync(projectPath)) {
        dialog.showErrorBox(
            'File Not Found',
            `The project file could not be found:\n${projectPath}\n\nIt may have been moved or deleted.`
        );
        removeFromRecentProjects(projectPath);
        return;
    }
    
    currentProjectPath = projectPath;
    setDatabasePath(projectPath);
    updateWindowTitle();
    addToRecentProjects(projectPath);
}

// Create menu
function createMenu() {
    const isMac = process.platform === 'darwin';
    
    const template = [
        // App menu (Mac only)
        ...(isMac ? [{
            label: app.name,
            submenu: [
                { role: 'about' },
                { type: 'separator' },
                { role: 'hide' },
                { role: 'hideOthers' },
                { role: 'unhide' },
                { type: 'separator' },
                {
                    label: 'Quit VFX Shot Tracker',
                    accelerator: 'Cmd+Q',
                    click: () => {
                        stopFlask();
                        setTimeout(() => app.quit(), 1000);
                    }
                }
            ]
        }] : []),
        
        // File menu
        {
            label: 'File',
            submenu: [
                {
                    label: 'New Project',
                    accelerator: 'CmdOrCtrl+N',
                    click: newProject
                },
                {
                    label: 'Open Project...',
                    accelerator: 'CmdOrCtrl+O',
                    click: openProject
                },
                {
                    label: 'Open Recent',
                    submenu: recentProjects.length > 0 
                        ? [
                            ...recentProjects.map(projectPath => ({
                                label: path.basename(projectPath),
                                click: () => openRecentProject(projectPath)
                            })),
                            { type: 'separator' },
                            {
                                label: 'Clear Recent Projects',
                                click: () => {
                                    recentProjects = [];
                                    saveRecentProjects();
                                    createMenu();
                                }
                            }
                        ]
                        : [{ label: 'No Recent Projects', enabled: false }]
                },
                { type: 'separator' },
                {
                    label: currentProjectPath 
                        ? `Save Project (${path.basename(currentProjectPath)})`
                        : 'Save Project',
                    accelerator: 'CmdOrCtrl+S',
                    enabled: currentProjectPath !== null,
                    click: saveProject
                },
                {
                    label: 'Save Project As...',
                    click: saveProjectAs
                },
                { type: 'separator' },
                {
                    label: 'Close Project',
                    accelerator: 'CmdOrCtrl+W',
                    click: () => {
                        if (mainWindow) mainWindow.close();
                    }
                },
                ...(!isMac ? [
                    { type: 'separator' },
                    {
                        label: 'Quit',
                        accelerator: 'Ctrl+Q',
                        click: () => {
                            stopFlask();
                            setTimeout(() => app.quit(), 1000);
                        }
                    }
                ] : [])
            ]
        },
        
        // Edit menu
        {
            label: 'Edit',
            submenu: [
                { role: 'undo' },
                { role: 'redo' },
                { type: 'separator' },
                { role: 'cut' },
                { role: 'copy' },
                { role: 'paste' },
                { role: 'selectAll' }
            ]
        },
        
        // View menu
        {
            label: 'View',
            submenu: [
                {
                    label: 'Zoom In',
                    accelerator: 'CmdOrCtrl+Plus',
                    click: () => {
                        const factor = mainWindow.webContents.getZoomFactor();
                        mainWindow.webContents.setZoomFactor(factor + 0.1);
                    }
                },
                {
                    label: 'Zoom Out',
                    accelerator: 'CmdOrCtrl+-',
                    click: () => {
                        const factor = mainWindow.webContents.getZoomFactor();
                        mainWindow.webContents.setZoomFactor(factor - 0.1);
                    }
                },
                {
                    label: 'Actual Size',
                    accelerator: 'CmdOrCtrl+0',
                    click: () => {
                        mainWindow.webContents.setZoomFactor(1.0);
                    }
                },
                { type: 'separator' },
                {
                    label: 'Toggle Full Screen',
                    accelerator: isMac ? 'Ctrl+Cmd+F' : 'F11',
                    click: () => {
                        mainWindow.setFullScreen(!mainWindow.isFullScreen());
                    }
                },
                { type: 'separator' },
                {
                    label: 'Toggle Developer Tools',
                    accelerator: isMac ? 'Cmd+Option+I' : 'Ctrl+Shift+I',
                    click: () => {
                        mainWindow.webContents.toggleDevTools();
                    }
                }
            ]
        },
        
        // Window menu
        {
            label: 'Window',
            submenu: [
                {
                    label: 'Minimize',
                    accelerator: 'CmdOrCtrl+M',
                    role: 'minimize'
                },
                ...(isMac ? [
                    { type: 'separator' },
                    {
                        label: 'Bring All to Front',
                        role: 'front'
                    }
                ] : [])
            ]
        }
    ];

    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);
}

// App lifecycle
// Handle export file save dialogs
let lastExportPaths = {
    edl: null,
    pdf: null,
    csv: null
};

ipcMain.handle('save-export-dialog', async (event, options) => {
    const { type, defaultFilename } = options;
    
    // Get last used path for this export type
    const defaultPath = lastExportPaths[type] 
        ? path.join(lastExportPaths[type], defaultFilename)
        : defaultFilename;
    
    const result = await dialog.showSaveDialog(mainWindow, {
        title: `Save ${type.toUpperCase()} File`,
        defaultPath: defaultPath,
        filters: [
            { name: `${type.toUpperCase()} Files`, extensions: [type] },
            { name: 'All Files', extensions: ['*'] }
        ]
    });
    
    if (!result.canceled) {
        // Remember the directory for next time
        lastExportPaths[type] = path.dirname(result.filePath);
        return { success: true, filePath: result.filePath };
    }
    
    return { success: false };
});

// Handle actual file writing
// Folder picker for split PDF exports
ipcMain.handle('pick-folder', async (event) => {
    const result = await dialog.showOpenDialog({
        title: 'Select Folder for PDFs',
        properties: ['openDirectory', 'createDirectory']
    });
    
    if (result.canceled || result.filePaths.length === 0) {
        return { success: false };
    }
    
    return { 
        success: true, 
        folderPath: result.filePaths[0]
    };
});

ipcMain.handle('write-export-file', async (event, { filePath, data }) => {
    try {
        // Data comes as base64 or text
        const buffer = Buffer.from(data, 'base64');
        fs.writeFileSync(filePath, buffer);
        return { success: true };
    } catch (error) {
        console.error('Error writing file:', error);
        return { success: false, error: error.message };
    }
});

// Handle picker actions via IPC
ipcMain.on('picker-action', (event, action) => {
    console.log('Picker action received:', action);
    
    // Close all picker windows
    BrowserWindow.getAllWindows().forEach(win => {
        if (win.getTitle() === 'VFX Shot Tracker') {
            win.close();
        }
    });
    
    if (action === 'new-project') {
        // Show dialog immediately
        dialog.showSaveDialog(null, {
            title: 'Create New Project',
            defaultPath: 'untitled_project.db',
            filters: [{ name: 'VFX Tracker Project', extensions: ['db'] }]
        }).then(result => {
            if (!result.canceled) {
                currentProjectPath = result.filePath;
                console.log('Creating new project at:', currentProjectPath);
                
                // Store path for Flask to use
                process.env.VFX_DB_PATH = currentProjectPath;
                
                // Create database via API
                fetch('http://localhost:5001/api/set_database_path', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: currentProjectPath })
                })
                .then(response => {
                    if (!response.ok) throw new Error('Database creation failed');
                    return response.json();
                })
                .then(data => {
                    console.log('Database created, restarting Flask...');
                    addToRecentProjects(currentProjectPath);
                    
                    // Restart Flask to pick up new database
                    stopFlask();
                    
                    setTimeout(() => {
                        startFlask();
                        
                        // Wait longer for Flask to fully restart
                        setTimeout(() => {
                            // NOW create window
                            createWindow();
                            createMenu();
                            updateWindowTitle();
                        }, 3000);
                    }, 1000);
                })
                .catch(error => {
                    console.error('Error creating project:', error);
                    dialog.showErrorBox('Error', 'Failed to create new project: ' + error.message);
                    showProjectPicker();
                });
            } else {
                console.log('New project cancelled');
                showProjectPicker();
            }
        });
    } else if (action === 'open-project') {
        // Show dialog immediately
        dialog.showOpenDialog(null, {
            title: 'Open Project',
            filters: [
                { name: 'VFX Tracker Project', extensions: ['db'] },
                { name: 'All Files', extensions: ['*'] }
            ],
            properties: ['openFile']
        }).then(result => {
            if (!result.canceled && result.filePaths.length > 0) {
                const selectedPath = result.filePaths[0];
                
                if (!fs.existsSync(selectedPath)) {
                    dialog.showErrorBox('File Not Found', 'Could not find: ' + selectedPath);
                    showProjectPicker();
                    return;
                }
                
                currentProjectPath = selectedPath;
                process.env.VFX_DB_PATH = selectedPath;
                addToRecentProjects(selectedPath);
                
                // Restart Flask with correct database BEFORE showing window
                stopFlask();
                setTimeout(() => {
                    startFlask();
                    waitForFlask().then(ready => {
                        if (ready) {
                            createWindow();
                            createMenu();
                            updateWindowTitle();
                        } else {
                            dialog.showErrorBox('Error', 'Flask failed to start');
                            showProjectPicker();
                        }
                    });
                }, 500);
            } else {
                showProjectPicker();
            }
        });
    } else if (action.startsWith('recent-')) {
        const idx = parseInt(action.split('-')[1]);
        const projectPath = recentProjects[idx];
        
        if (fs.existsSync(projectPath)) {
            currentProjectPath = projectPath;
            process.env.VFX_DB_PATH = projectPath;
            addToRecentProjects(projectPath);
            
            // Restart Flask with correct database BEFORE showing window
            stopFlask();
            setTimeout(() => {
                startFlask();
                waitForFlask().then(ready => {
                    if (ready) {
                        createWindow();
                        createMenu();
                        updateWindowTitle();
                    } else {
                        dialog.showErrorBox('Error', 'Flask failed to start');
                        showProjectPicker();
                    }
                });
            }, 500);
        } else {
            dialog.showErrorBox('File Not Found', `Could not find: ${projectPath}`);
            removeFromRecentProjects(projectPath);
            showProjectPicker();
        }
    }
});

app.whenReady().then(async () => {
    loadRecentProjects();
    startFlask();
    
    // Wait for Flask to be ready
    const flaskReady = await waitForFlask();
    
    if (flaskReady) {
        showProjectPicker();
        createMenu();
    } else {
        dialog.showErrorBox(
            'Startup Error',
            'Flask server failed to start. Check Console.app for details.'
        );
        app.quit();
    }
});

app.on('window-all-closed', () => {
    console.log('All windows closed');
    // On Windows, quit when all windows are closed
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('before-quit', () => {
    console.log('App quitting, stopping Flask...');
    stopFlask();
});

app.on('will-quit', () => {
    console.log('App will quit, ensuring Flask is stopped...');
    stopFlask();
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});
