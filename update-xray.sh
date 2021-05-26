#!/bin/bash

cd bin

last_version=$(curl -Ls "https://api.github.com/repos/XTLS/Xray-core/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
if [[ ! -n "$last_version" ]]; then
    echo -e "检测最新版本失败"
    exit 1
fi
wget -O xray.zip https://github.com/XTLS/Xray-core/releases/download/${last_version}/Xray-linux-64.zip
unzip xray.zip -d temp

rm xray-v2-ui geoip.dat geosite.dat -f

mv temp/xray ./xray-v2-ui
mv temp/geoip.dat ./
mv temp/geosite.dat ./

chmod +x xray-v2-ui

rm temp xray.zip -rf

echo "更新版本 ${last_version} 成功"
