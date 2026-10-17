; Tauri NSIS hooks (bundle.windows.nsis.installerHooks).
;
; Versions before the Job Object fix could leave drafter-backend.exe running after the app was
; closed. The orphan keeps the backend's files open, and the copy fails with "cannot open file
; for writing". Stop it before files are copied or removed, and give Windows a moment to release
; the files.

!macro DRAFTER_STOP_BACKEND
  nsExec::Exec 'taskkill /F /T /IM drafter-backend.exe'
  Pop $0
  Sleep 1000
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro DRAFTER_STOP_BACKEND
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro DRAFTER_STOP_BACKEND
!macroend
