function out=draw_height_depth_warning_scheme(output_folder)
% 用示意图说明：旧统计值仍可打印，但50 mm相对深度不能直接拼接190 mm参考面。
if nargin<1||isempty(output_folder),output_folder=fileparts(mfilename('fullpath'));end
if ~isfolder(output_folder),mkdir(output_folder);end
x=linspace(0,10,500); H=.62-.08*sin(1.2*x)-.18*exp(-((x-3.2)/.55).^2)-.23*exp(-((x-7.5)/.7).^2);
Htop=max(H); H0=.95; Drel=Htop-H;
f=figure('Visible','off','Color','w','Position',[100 100 1200 650]);
tiledlayout(2,1,'TileSpacing','compact','Padding','compact');
nexttile; plot(x,H,'k','LineWidth',2);hold on; yline(Htop,'r--','H_{top}=max(H)');yline(H0,'b--','H_0 未腐蚀参考面');
fill([x fliplr(x)],[H Htop*ones(size(H))],[.25 .75 .9],'FaceAlpha',.35,'EdgeColor','none');plot(x,H,'k','LineWidth',2);
text(3.2,.38,'坑底（H较低）','Color',[.7 0 0]); text(7.5,.22,'坑底（H较低）','Color',[.7 0 0]);
text(.3,(H0+Htop)/2,'均匀分量\newlineH_0-H_{top}','Color','b'); text(9.0,(Htop+mean(H))/2,'不均匀分量\newlineH_{top}-mean(H)','Color','r');
xlabel('扫描位置');ylabel('齐平高程 H / mm');title('A. 原程序保留的高程与参考面定义');grid on;legend('H(x)','H_{top}','H_0','Location','southwest');
nexttile; plot(x,Drel,'Color',[.85 .1 .1],'LineWidth',2);yline(0,'k--');hold on;
scatter([3.2 7.5],interp1(x,Drel,[3.2 7.5]),45,'r','filled');
xlabel('扫描位置');ylabel('相对深度 D_{relative}=H_{top}-H / mm');title('B. 正向出图：只把显示零点移到H_{top}，不改变坑底识别');grid on;
annotation(f,'textbox',[.12 .005 .76 .045],'String','警告原因：H_{top}-H是相对深度；H_0-H才是总腐蚀深度。190 mm的H_0与独立齐平的50 mm高程尚未证明同一基准，因此导出接口阻止CA-GA自动拼接。','EdgeColor','none','HorizontalAlignment','center','FontSize',11);
out=fullfile(output_folder,'高程_正向深度_参考面关系示意图.png');exportgraphics(f,out,'Resolution',180);close(f);
end
