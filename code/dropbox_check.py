import dropbox

# 請替換成您的 Dropbox 存取權杖
ACCESS_TOKEN = "sl.u.AFnSlWXOaSd9VuYdvUihjSgsRzbzq6Das1lT8e_5P-ue65cqU-3F37SHccj1VpHqP4Jgx5oGl4xJpc6cXehKspqErZ5ckuTQdeUuz3zUG6M62kV2ibpwycYZ6Xt0jIaV2QVvvfhTnP5EazgSVdTNK1bpeomLSjDcHEriOBHtDsaVjkgl7W0u5jOOjvQvM-LZUwjAxaDEK6g6KmalE9X-guY2UvG52bGjceGdjl1gpBfyCC0WK4IQbSG7b9F9ZoVJzhtRzlld3y86kQzDq4f6CUCxeM1fnpJYOS5hO3FEfKxrTWx1zKm9Zzb0wcHjQzFMfcXhBqkDbfYUlfdpfMTwEyoeh6N2BOVuN67sMoMo6I4zVcWxzpEHCQ1MQNKkmE1MfgfgxWCIy_AMhTAu0xlEkHute-DKwBsdiIe5sUQ8_gHhjN1HL3AAU0RSM643BTTOIcG248xMhF29UT8dZmfORWLpVnbSnevaRsa2G-U9Z7RCME8LezWxf05wx7CvI0PtEGqXNG-XfdsRvVOS4tP4lcuaELnR-6QdkC14oZbIMVBCXnkH2ou8vuw1zmXOMnXhOqHYDkAPCz2jDPYMBokK3uaIaRlqvnFMHDKAZ2Gh_ohMGCN8YjJno9iBQMBcA__qkGOesDmLnDFF5Fk6i9-773EzoyLK3l_jM7JtBUMRQrBjDzBhus3SsYCya0K471zcRXFckY4OQOvqzpXaV4zRJFftCtgE1_Rc6_Tpxb2zTq1_nETG4TWl0i6Rn8vLbvHY1Wdfb1ezeZPgJK_3xNtFXojqVb2t-pY9TiFe7FBOVSLeqnWBY0kcdsYLW0HbjpLrFjy0tzn4zTCmcZAUbT4zGv14_ZzRP9hKWfcRM-fq246_dj3xDhf6uUz-5h0X3DlgkrsLN_9z-fizaOK_OXajJ6unXx-d29AMYaRtJMo4vuJwksIbf68Rd5En8xGzCG9Ff2pGBoHHsXNcEPCaPbh8vHUNBSSeRgwLNEmRKfYN6D9Z2NeXGFHzeO4UIvyRxBFQfvzNcgIYfXpJs0o3PieVF_tEhcfjrm9b5FpZdFMwZTBHvtPAO7HSfGZw53iBb1zrkQ_Y6l1Ti2Fkf-rc4mnjJU6AgCW-36GfoqP7gv49823GwZZzT2jbPonBCKcyvXThoXmHO1YIy9lFlQWbGa8XZur7mbxxTX3PFQgTcEYALImmgjj_ay7jGU6R5kpTpls063JYs4J0EUhrEZJsTKiKSNQSAm4hBILhuyNBGP0qKEhpqvTCJF6PahrfV2vIvpLPsLnTxxR6EqAUhs8RtBDmYJKS"

# 設定要列出內容的資料夾路徑：
# 若為 App folder 型態，若要列出根目錄，請傳入空字串 ""；若為全 Dropbox，請傳入正確的絕對路徑，例如 "/Apps/CoralNet_test"
folder_path = ""  

dbx = dropbox.Dropbox(ACCESS_TOKEN)

def list_folder(path, indent=0):
    try:
        result = dbx.files_list_folder(path)
        for entry in result.entries:
            print("  " * indent + f"- {entry.name} ({type(entry).__name__})")
            # 如果是資料夾則遞迴呼叫列出子項目
            if isinstance(entry, dropbox.files.FolderMetadata):
                list_folder(entry.path_lower, indent + 1)
    except Exception as e:
        print("列出資料夾", path, "時發生錯誤：", e)

# 列出指定路徑下的檔案與資料夾
print("目前 Dropbox 資料夾結構：")
list_folder(folder_path)
