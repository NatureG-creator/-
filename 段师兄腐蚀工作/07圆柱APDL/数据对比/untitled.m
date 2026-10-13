figure('Color','w','Position',[100,100,800,500]);
hold on; grid on;

% 拟合密度（越大越光滑）
fit_density = 1000;  

% ========== 绘制数据1 光滑曲线（已修复去重） ==========
t1 = moni(:,1)*1.0;
f1 = moni(:,2)*1.00;

% 关键修复：去重 + 排序
[t1_unique, idx] = unique(t1);
f1_unique = f1(idx);

t1_fit = linspace(min(t1_unique), max(t1_unique), fit_density);
f1_fit = spline(t1_unique, f1_unique, t1_fit);  
plot(t1_fit, f1_fit, 'b-', 'LineWidth',2.5);  

% ========== 绘制数据2 光滑曲线（已修复去重） ==========
t2 = zhenshi(:,1);
f2 = zhenshi(:,2);

% 关键修复：去重 + 排序
[t2_unique, idx] = unique(t2);
f2_unique = f2(idx);

t2_fit = linspace(min(t2_unique), max(t2_unique), fit_density);
f2_fit = spline(t2_unique, f2_unique, t2_fit);
plot(t2_fit, f2_fit, 'r-', 'LineWidth',2.5);  

%% ===================== 图表设置 =====================
xlabel('$L$ (mm)','FontSize',18,'FontWeight','bold','Interpreter','latex','FontName','Times New Roman');
ylabel('$\sigma$ (MPa)','FontSize',18,'FontWeight','bold','Interpreter','latex','FontName','Times New Roman');
legend('Simulation','Experiment','Location','best','FontSize',14,'FontName','Times New Roman');
set(gca,'FontSize',18,'LineWidth',1,'FontName','Times New Roman');