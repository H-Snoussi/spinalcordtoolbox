function sct_export_m(func)
% sct_export_m(func)
% EXAMPLE: sct_export_m('imagesc3D.m')
dep=matlab.codetools.requiredFilesAndProducts(func); [~,func]=fileparts(func);
disp(dep')
dep = dep(cellfun(@isempty,strfind(dep,[func '.m'])));
mkdir(func)
copyfile(which(func),func)
for idep=1:length(dep)
    copyfile(dep{idep},[func filesep sct_tool_remove_extension(dep{idep},0) '.m'] ); %     copyfile(dep{idep},[func filesep func '_' sct_tool_remove_extension(dep{idep},0) '.m'] )
    %filedep{idep} = [func filesep func '_' sct_tool_remove_extension(dep{idep},0) '.m'];
end





%% Determine files to manipulate

%cd(func)



% %% Manipulieren der verweneten Dateien
% 
% disp('Manipulated Files:');
% 
% for idx = 1 : length(dep)
%     oldString           = sct_tool_remove_extension(dep{idx},0);
%     newString           = [func '_' sct_tool_remove_extension(dep{idx},0)];
%     regularExpression   = '[\w]+\.m';
% 
%     if (~isempty ( regexp(dep{idx}, '[\w]+\.m','match') )) & isempty(strfind(dep{idx},[func '.m']))
% 
%         disp(dep{idx});
%         
%         % Read and manipulate Text
%         fileIdRead  = fopen(dep{idx}, 'r');
%         fileText    = fscanf(fileIdRead,'%c');
% 
%         fileTextNew = strrep(fileText, oldString, newString);
% 
%         fclose(fileIdRead);
%         
%         
% 
%         % Write Text
%         fileIdWrite = fopen(dep{idx}, 'w');
% 
%         fprintf(fileIdWrite, '%c', fileTextNew);
% 
%         fclose(fileIdWrite);
%     end
% 
% end
% cd ..   
% %% ZIP
 zip(func,func)