Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\proyecto_Asistencia" 
WshShell.Run "cmd.exe /c C:\proyecto_Asistencia\arranca_sistema.bat", 0, False