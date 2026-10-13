function fenbujianyan(data)
% Import data
% Visualize data distribution
figure;
% Use scientific low-saturation blue color scheme
histogram(data, 'BinWidth', 0.1, 'Normalization', 'pdf', 'FaceColor', [0 0.45 0.74]);
hold on;

% Set axis tick numbers font (Times New Roman, size 14)
set(gca, 'FontName', 'Times New Roman', 'FontSize', 16);

% Set labels and title with Times New Roman, size 14
xlabel('Corrison Depth', 'FontName', 'Times New Roman', 'FontSize', 16); 
ylabel('Probability Density', 'FontName', 'Times New Roman', 'FontSize', 16);
title('Data Histogram and Fitting Curve', 'FontName', 'Times New Roman', 'FontSize', 16);

% Calculate normal distribution parameters (mean mu, standard deviation sigma)
[mu, sigma] = normfit(data);
% Or use distribution fitting object
pd = fitdist(data, 'Normal');
mu = pd.mu;       % Mean
sigma = pd.sigma; % Standard deviation

disp(['Mean μ = ', num2str(mu)]);
disp(['Standard Deviation σ = ', num2str(sigma)]);

% Generate theoretical normal distribution curve
x = linspace(min(data), max(data), 1000);
pdf_normal = normpdf(x, mu, sigma);

% Overlay plot
plot(x, pdf_normal, 'r-', 'LineWidth', 2);
% Set legend with Times New Roman, size 12
legend('Data Distribution', 'Fitted Normal Curve', 'FontName', 'Times New Roman', 'FontSize', 12);

% Q-Q plot for normality test
%figure;
%qqplot(data);
% Set same font properties for Q-Q plot
%set(gca, 'FontName', 'Times New Roman', 'FontSize', 14);
%title('Q-Q Plot for Normality Test', 'FontName', 'Times New Roman', 'FontSize', 14);
end