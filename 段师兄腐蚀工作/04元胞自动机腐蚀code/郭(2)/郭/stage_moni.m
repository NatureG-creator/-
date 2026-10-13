%引入不同阶段对应参数
%date_x为质量损失率
%date1,date2为均匀质量损失和不均匀质量损失
%data3-jsb_标准差
%clc
%clear
%初始元胞尺寸
%长宽高
w=100;
l=100;
n=100;
data_x=48;
data_y=158;
data1=2.09;
data2=5.48;
data3=0.66;
data4=0.28;
data=[data_x' data_y' data1' data2' data3' data4'];
parameter_single=10;%参数个数
%即每代元胞自动机质量损失率不超过F次
        space=25;
        F=100;
        stage_number=1;
        a_input=[];
        d_input=[];
        cl_input=[];
        % a_input=a_output;
        % d_input=d_output;
        % cl_input=cl_output;
        perfect_result_sd=zeros(size(data_x,2),size(data,2)-2);
        perfect_parameter_sd=zeros(size(data_x,2),parameter_single);
        a_sd=cell(size(data_x,2),1);
for i=1:size(data_x,2)
        [perfect_result,perfect_parameter,a_output,d_output,cl_output]=GA(w,l,n,data_x(i),data(i,:),a_input,F,stage_number,space,d_input,cl_input);
        perfect_result_sd(i,:)=perfect_result;
        perfect_parameter_sd(i,:)=perfect_parameter;
        a_sd{i}=a_output;
        a_input=a_output;
        d_input=d_output;
        cl_input=cl_output;
        stage_number=stage_number+1;
end
