from PyInstaller.utils.hooks import copy_metadata
datas = copy_metadata('opentimelineio')
datas += copy_metadata('otio_cmx3600_adapter')
datas += copy_metadata('otio_ale_adapter')
datas += copy_metadata('opentimelineio-plugins')
