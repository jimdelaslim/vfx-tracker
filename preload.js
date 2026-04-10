const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electron', {
    // Send database path to Flask
    setDatabasePath: (path) => ipcRenderer.send('set-database-path', path),
    
    // Get current database path
    getDatabasePath: () => ipcRenderer.invoke('get-database-path'),
    
    // Notify when database is ready
    onDatabaseReady: (callback) => ipcRenderer.on('database-ready', callback),
    
    // Export file dialogs
    saveExportDialog: (options) => ipcRenderer.invoke('save-export-dialog', options),
    writeExportFile: (data) => ipcRenderer.invoke('write-export-file', data),
    pickFolder: () => ipcRenderer.invoke('pick-folder'),
    
    // Clipboard access
    clipboard: {
        writeText: (text) => require('electron').clipboard.writeText(text),
        readText: () => require('electron').clipboard.readText()
    }
});
