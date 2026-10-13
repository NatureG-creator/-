function c=height_depth_components(H,H0,reference_verified)
% H为原齐平高程；低处是坑底。正深度显示不代表已知未腐蚀参考面。
if nargin<2,H0=NaN;end
if nargin<3,reference_verified=false;end
assert(ismatrix(H)&&~isempty(H)&&all(isfinite(H(:))), ...
    'depth:InvalidHeight','补齐高程矩阵必须完整且有限。');
assert(isscalar(H0)&&isreal(H0)&&(isfinite(H0)||isnan(H0)), ...
    'depth:InvalidReference','参考高度必须为有限标量或未知值NaN。');
assert(isscalar(reference_verified)&&(islogical(reference_verified)|| ...
    ismember(reference_verified,[0 1])),'depth:InvalidVerification','参考确认必须为逻辑标量。');
assert(~reference_verified||isfinite(H0),'depth:MissingReference','确认参考面前必须提供同高程基准的H0。');
c=struct('surface_top_mm',max(H(:)),'relative_depth_mm',max(H(:))-H, ...
    'nonuniform_depth_mm',max(H(:))-mean(H(:)), ...
    'reference_height_mm',H0,'reference_verified',logical(reference_verified), ...
    'uniform_depth_mm',NaN,'mean_total_depth_mm',NaN,'total_depth_mm',NaN(size(H)));
if reference_verified
    % 对应示意图：总深度=均匀分量+相对起伏；不自动取绝对值。
    c.total_depth_mm=H0-H;
    c.uniform_depth_mm=H0-c.surface_top_mm;
    c.mean_total_depth_mm=H0-mean(H(:));
end
end
