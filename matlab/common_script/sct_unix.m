function sct_unix(cmd)
disp(['<strong> >> ' cmd '</strong>']);
status=unix(cmd);
if status, disp('ERROR!!!!!!!!!! Press ok to continue, or ctrl+c to stop the program'); pause; end