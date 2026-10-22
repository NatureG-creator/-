function tests=test_export_original_ca_target_joint
tests=functiontests(localfunctions);
end

function testLogSamplesUseCommonValidPitMask(testCase)
cfg=step00_corrosion_config();
raw=reshape(1:16,4,4)/1000;
source=[tempname '.txt'];
writematrix([1 2 3],source);
output_base=tempname;
mkdir(output_base);
cleanup=onCleanup(@()cleanup_fixture(source,output_base)); %#ok<NASGU>
old_name=getenv('CORROSION_DATA_NAME');
old_base=getenv('CORROSION_OUTPUT_BASE');
restore=onCleanup(@()restore_environment(old_name,old_base)); %#ok<NASGU>
setenv('CORROSION_DATA_NAME','joint_fixture');
setenv('CORROSION_OUTPUT_BASE',output_base);
pit_depth=[.01;.02;.03];diameter=[0;.15;.2];ratio=[.1;.2;.3];
[~,result]=export_original_ca_target(raw,raw,min(raw(:)),pit_depth,ratio,diameter,[1 1;2 2;3 3],cfg, ...
    struct('point_cloud_190',source,'point_cloud_50',source),output_base);
verifyEqual(testCase,numel(result.original_shengdu_mm),3);
verifyEqual(testCase,result.log_depth,log(pit_depth(2:3)*1000),'AbsTol',1e-12);
verifyEqual(testCase,result.log_ratio,log(1./ratio(2:3)),'AbsTol',1e-12);
verifyEqual(testCase,result.pit_count,2);
verifyTrue(testCase,result.calibration_ready);
end

function restore_environment(old_name,old_base)
setenv('CORROSION_DATA_NAME',old_name);
setenv('CORROSION_OUTPUT_BASE',old_base);
end

function delete_if_exists(path)
if isfile(path),delete(path);end
end

function cleanup_fixture(source,output_base)
delete_if_exists(source);
if isfolder(output_base),rmdir(output_base,'s');end
end
