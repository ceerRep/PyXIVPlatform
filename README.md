
# PyXIVPlatform

## 简介
这是一个非常简单的 FFXIV 脚本平台  
目前可以读内存日志和自动搓东西、钓鱼  
有空会迁移到 Java 上， Python版目前停止更新，仅不定期更新偏移  
（因为当时决定不再更新所以 craftbot 插件代码乱的离谱（（（  

当 `run.py` 执行后，它会从前至后读取参数列表中的配置目录，较后的配置会覆盖较前配置中相同的项

## 插件配置
- `CommandHelper`
	- 提供了非常基础的命令服务
- `XIVMemory`
	- 提供与 FFXIV 进程相关的接口
	- 配置：
		- `scan_interval` 扫描间隔，单位毫秒
		- `key_press_delay` 按键间隔，单位毫秒
		- `find_xiv_by_player_name` 是否根据 `player.name` 查找 FFXIV 进程
	- `LogScanner`
		- 提供了 FFXIV 内存日志相关接口，并在 `CommandHelper` 中注册了 FFXIV 内部聊天框的输入输出流
- `PostNamazuWrapper`
	- 与鲇鱼精邮差交互的插件
	- 配置：
		- `post_namazu_addr` 鲇鱼精邮差 api 地址
- `CraftBot`
	- 提供与制作和钓鱼有关的一系列功能
	- 配置：
		- `recipes_dir` 制作脚本位置
		- `retry_count` 使用技能重试次数
		- `retry_timeout` 使用技能超时时间
		- `delay_after_action` 每次使用技能后延迟
	- 命令:
		- `craft`
			- `/e /craft recipe num`
			- 搓指定配方 n 次
		- `stopcraft`
			- `/e /stopcraft`
			- 停止 CraftBot 插件当前动作
		- `autohandin`
			- 自动交物品，我也忘了这玩意咋用
		- `autofish` 
			- `/e /autofish walktime threshold`
			- 自动钓鱼，自动轻重钩，鱼王钩应该是写死在代码里的  
			代码里注释部分可以自动开耐心钓收(bai)藏(piao)品
			- 只有咬钩时间大于 `threshold` 且能收藏的鱼会变成收藏品  
			- 当鱼很警惕就会自动调用 `/changeplace walktime`，walktime 每次取反
		- `changeplace`
			- `/e /changeplace time`
			- 自动朝左或右走一定时间，会先尝试动一下收杆  
			- 正负怎么对应左右忘了  
		- `jump`
			- `/e /jump time`
			- 每隔一定时间跳一下
			- 挂机用

## 使用方法

### 配置

`config_user_CN` 和 `config_user_Global` 是国服和国际服的默认用户配置文件夹，你也可以参照 `runCN.bat` 使用自己的配置文件夹。

```
powershell.exe -Command python run.py config_common config_CN config_user_114514
```

这样是使用 `config_user_114514` 文件夹。  
程序读取配置时会按照从前往后的顺序在文件夹中读取，即 `config_user_114514` 覆盖 `config_CN`, `config_CN` 覆盖 `config_common`。

### 配置用户名
在对应的用户文件夹新建 `player.json`，内容如下。

```json
{
    "name": "<角色名>"
}
```

程序会尝试打开匹配的 FFXIV 进程。
