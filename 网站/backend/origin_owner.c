#include <Origin.h>
#include <mswin.h>

// Executed inside the dedicated COM instance, never inferred from global PIDs.
int CorrosionOriginProcessID()
{
    return (int)GetCurrentProcessId();
}

int CorrosionOriginExportTheme(string path)
{
    GraphLayer gl = Project.ActiveLayer();
    Tree tr;
    tr = gl.GetFormat(FPB_ALL, FOB_ALL, TRUE, TRUE);
    return tr.Save(path);
}

int CorrosionOriginApplyTheme(string path)
{
    Tree tr;
    if (!tr.Load(path))
        return 0;
    GraphLayer gl = Project.ActiveLayer();
    return gl.ApplyFormat(tr, TRUE, TRUE);
}
