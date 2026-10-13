function out=draw_c17_three_metrics_scheme(output_folder)
% 将C17旧程序的三个统计量放在同一张解释图中。
if nargin<1||isempty(output_folder),output_folder=fileparts(mfilename('fullpath'));end
if ~isfolder(output_folder),mkdir(output_folder);end
uniform=0.696670; uniform_signed=-0.696670; pit_mean_um=335.1606; nonuniform=0.262440;
f=figure('Visible','off','Color','w','Position',[80 80 1400 760]);
tiledlayout(1,2,'TileSpacing','compact','Padding','compact');
% 左图：实际数值比较，均匀分量按物理正方向显示。
nexttile;
vals=[uniform,nonuniform,pit_mean_um/1000];
b=bar(vals,'FaceColor','flat','BarWidth',.58); b.CData=[.20 .40 .85; .90 .35 .12; .15 .65 .35];
hold on; yline(0,'k-','LineWidth',1);
set(gca,'XTick',1:3,'XTickLabel',{'均匀分量','不均匀深度','平均坑深'},'FontSize',12);
ylabel('数值 / mm'); title('C17旧程序三个统计量'); grid on; box on;
text(1,uniform+.04,sprintf('+%.6f mm',uniform),'HorizontalAlignment','center','Color',[.1 .2 .6],'FontWeight','bold');
text(2,nonuniform+.04,sprintf('%.6f mm',nonuniform),'HorizontalAlignment','center','Color',[.7 .2 .05],'FontWeight','bold');
text(3,pit_mean_um/1000+.04,sprintf('%.4f mm (%0.4f \mum)',pit_mean_um/1000,pit_mean_um),'HorizontalAlignment','center','Color',[.05 .45 .2],'FontWeight','bold');
ylim([-0.9 .55]);
% 右图：定义关系，同时标出旧程序的反向差值。
nexttile;
x=linspace(0,10,600); H=.52-.06*sin(1.4*x)-.17*exp(-((x-3.1)/.5).^2)-.21*exp(-((x-7.5)/.65).^2);
Htop=max(H); H0=Htop+0.22;
plot(x,H,'k','LineWidth',2); hold on; yline(Htop,'r--','H_{top}'); yline(H0,'b--','H_0');
fill([x fliplr(x)],[H Htop*ones(size(H))],[.3 .75 .9],'FaceAlpha',.25,'EdgeColor','none'); plot(x,H,'k','LineWidth',2);
plot([3.1 7.5],[interp1(x,H,3.1) interp1(x,H,7.5)],'ro','MarkerFaceColor','r');
text(.35,(H0+Htop)/2,sprintf('均匀分量\nH_0-H_{top}\n旧值 = %.6f mm',uniform),'Color',[.05 .2 .8],'FontSize',11);
text(7.85,(Htop+mean(H))/2,sprintf('不均匀深度\nH_{top}-mean(H)\n= %.6f mm',nonuniform),'Color',[.75 .15 .05],'FontSize',11);
text(3.25,.18,sprintf('坑底\n平均坑深 = %.4f \mum',pit_mean_um),'Color',[.05 .45 .2],'FontSize',11);
xlabel('扫描位置'); ylabel('齐平高程 H / 示意值'); title('三个量在形貌中的定义'); grid on; box on;
legend('高程H','表面最高点','未腐蚀参考面','Location','southwest');
annotation(f,'textbox',[.08 .015 .84 .045],'String','注意：均匀分量保留旧程序的有符号值；平均坑深是16个识别坑的平均值，不等于均匀分量或总腐蚀深度。','EdgeColor','none','HorizontalAlignment','center','FontSize',12);
out=fullfile(output_folder,'C17_均匀分量_不均匀深度_平均坑深_示意图.png'); exportgraphics(f,out,'Resolution',180); close(f);
end
