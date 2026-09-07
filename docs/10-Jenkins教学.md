# Jenkins 教学（以 MiniMall 项目为例）

## 1. Jenkins 是什么？和 GitHub Actions 有什么不同

**一句话：** Jenkins 是可自己掌控的 CI/CD 服务器，GitHub Actions 是托管式 CI 服务。

| 维度 | GitHub Actions | Jenkins |
|---|---|---|
| 部署 | 托管在 GitHub，开箱即用 | **你自己部署**（一台服务器、Docker 或 K8s） |
| 配置位置 | `.github/workflows/*.yml` | `Jenkinsfile` 放在仓库根目录 |
| 触发 | GitHub 事件（push/PR） | 任何：webhook、定时、轮询、手动 |
| 插件 | 官方 actions 市场 | **1800+ 插件**，什么都能接（Jira、Sonar、K8s、Slack…） |
| 数据位置 | GitHub 服务器 | 你自己的机器 |
| 适合 | 开源、初创、公开项目 | **大厂内部项目、需要合规/定制的场景** |

**为什么大厂（包括字节/美团）还在大量用 Jenkins（或者在用它过渡到自研）：**
1. 插件生态无敌——接 JIRA 接飞书接 K8s 接自研系统，全有现成插件
2. 配置即代码（Jenkinsfile）但跑在你自己的机器上，**代码不出内网**
3. **排队规则、节点分配、定时调度**比 GitHub Actions 灵活几十倍
4. 老系统包袱——很多大厂 2015 年前就在用，迁移成本太高

---

## 2. 三种跑 Jenkins 的方式

| 方式 | 命令 | 适用 |
|---|---|---|
| **Docker（推荐）** | `docker run -p 8080:8080 jenkins/jenkins:lts` | 本地学习，3 分钟跑起来 |
| War 包（传统） | `java -jar jenkins.war` | 需要装 Java |
| Helm/K8s | `helm install jenkins jenkins/jenkins` | 生产环境 |

**Docker 是你现在唯一可行的方式**（你机器没装 Java，但 Docker 镜像自带 JRE）。一条命令搞定：

```bash
docker run -d ^
  --name jenkins ^
  -p 8080:8080 -p 50000:50000 ^
  -v jenkins_home:/var/jenkins_home ^
  jenkins/jenkins:lts
```

启动后浏览器访问 `http://localhost:8080`，第一次会让你输入初始密码（看容器日志 `docker logs jenkins`）。

---

## 3. 本项目的 Jenkinsfile 逐行讲解

我们的 `Jenkinsfile` 是 **declarative pipeline**（声明式流水线），结构固定为：

```
pipeline {
    agent any                // 在哪跑
    environment { ... }      // 全局环境变量
    triggers { ... }         // 触发规则
    options { ... }          // 流水线级选项
    
    stages {                 // 核心：每个 stage 是一段工作
        stage('A') { steps { ... } }
        stage('B') { steps { ... } }
    }
    
    post {                   // 后置：无论成败都执行
        always { ... }
        success { ... }
        failure { ... }
    }
}
```

### 关键 stage 含义

| Stage | 干了啥 |
|---|---|
| **Checkout** | `checkout scm` 自动从 Jenkins 里配的仓库拉代码 |
| **Prepare 被测服务** | 装 Flask 依赖 |
| **Install 测试依赖** | 装 pytest + requests + allure-pytest |
| **Start MiniMall 服务** | 后台启动被测系统（`nohup ... &`） |
| **Health Check** | curl 健康检查，失败直接 exit 1 |
| **Run 接口自动化** | 跑 pytest + 生成 Allure 结果 |
| **post.always** | 归档 Allure 结果（**无论成败都能下载**） |
| **post.cleanup** | 杀掉后台服务，避免下次跑端口冲突 |

### 为什么这么写（面试答题思路）

**问题1："Jenkins 里服务怎么后台启动？跑完怎么杀掉？"**
> 用 `nohup ... &` 后台启动，pid 写到 `$!`；post 阶段用 `pkill -f` 杀掉。**也可以用 `ProcessTreeKiller` 插件自动清。**

**问题2："Jenkins 怎么集成测试报告？"**
> Allure 推荐用 `allure-jenkins-plugin`：在 Jenkins 管理界面装插件，pipeline 里加 `allure([results: '...']/），它会自动渲染 HTML 报告页面（比 GitHub Actions 下载 artifact 再本地开爽 100 倍）。

**问题3："Jenkins 怎么跑分布式？"**
> 装多个 agent 节点（agent label `linux` / `mac` / `windows`），pipeline 里 `agent { label 'linux' }` 指定。**这就是大厂测开团队跑多环境回归的标准玩法**。

**问题4："Jenkins 怎么对接代码仓库？"**
> Jenkins UI → 凭据 → 添加 GitHub/GitLab 凭据 → 配 webhook 或用我们这种 `pollSCM('H/5 * * * *')` 每 5 分钟轮询。

---

## 4. 实战操作（本地 Docker 跑起来）

### 步骤 1：拉镜像启动

```bash
docker run -d ^
  --name jenkins ^
  -p 8080:8080 -p 50000:50000 ^
  -v jenkins_home:/var/jenkins_home ^
  jenkins/jenkins:lts
```

### 步骤 2：等 30 秒，访问 http://localhost:8080

### 步骤 3：解初始密码

```bash
docker logs jenkins 2>&1 | grep -A 1 "initial"
```

复制 `Please use the following password to proceed: ********` 那一行的密码。

### 步骤 4：装推荐插件（默认勾选全装即可）

### 步骤 5：建第一个 Pipeline Job

1. 主界面 → **New Item** → 名字 `MiniMall-Test` → 类型 **Pipeline** → 确定
2. **Pipeline** 配置区：
   - Definition: **Pipeline script from SCM**
   - SCM: **Git**
   - Repository URL: `https://github.com/你的用户名/mini-mall-test.git`
   - Script Path: `Jenkinsfile`
3. **Save** → 左侧 **Build Now** → 点进 #1 看实时日志

### 步骤 6：装 Allure 插件看报告

1. **Manage Jenkins** → **Manage Plugins** → Available → 搜 `Allure` → 装 `Allure Jenkins Plugin`
2. 项目配置里加构建后操作 **Allure Report**，Results path 填 `automation/reports/allure-results`
3. 下次构建后，**项目主页就有 Allure Report 图标**，点进去直接看 HTML 报告（比 GitHub Actions 下 artifact 解压省事 10 倍）

---

## 5. 大厂 Jenkins 实战场景（面试加分点）

| 场景 | Jenkins 怎么解决 | 你简历可以这么写 |
|---|---|---|
| **多环境回归** | Agent Label 按 OS 分组（win/mac/linux），同一 pipeline 在不同 agent 上各跑一遍 | "主导 X 项目 5 套环境自动化回归体系建设" |
| **定时夜间跑** | `triggers { cron('0 2 * * *') }` 凌晨2点全量回归 | "夜间定时回归覆盖 2000+ 用例" |
| **PR 拦截** | 配 GitHub PR Hook，分支有 PR 就跑测试 | "提交即跑，10 分钟内反馈" |
| **质量门禁** | 集成 SonarQube 插件，覆盖率/漏洞不过直接 fail | "集成 SonarQube，PR 卡口阻断不达标合并" |
| **CI 失败自动建 bug** | 集成 Jira 插件，失败自动开 ticket | "测试失败自动建缺陷到 Jira" |
| **并行执行** | `parallel { stage('X') { ... } stage('Y') { ... } }` | "接口/UI/性能并行跑，耗时从 30min 降到 8min" |

---

## 6. Jenkins vs 自研平台：怎么回答面试官

**Q："Jenkins 和大厂自研 CI（字节 ByteCycle、美团自研）的区别？"**
> 本质都是 Pipeline 即代码，区别在于规模化和定制能力。Jenkins 靠 1800+ 插件满足通用需求，但每个插件的配置/权限/审计/资源调度都要自己拼；大厂自研平台是把这些整合成原子能力，配合内部代码仓库、需求系统、AB 测试、监控告警形成闭环。**实习生进去不是用哪个工具的问题，是按团队 SOP 在平台上点按钮跑流程。** 所以我更看重工具背后的工程化思维：流水线分层、环境隔离、依赖缓存、并行调度、可观测性。

---

## 7. 你下一步建议

| 优先级 | 动作 | 时间 |
|---|---|---|
| ⭐⭐⭐ | 跟着步骤 1-6 在本地 Docker 跑起来，截图 Jenkins 主页+构建历史+Allure 报告页 | 30 分钟 |
| ⭐⭐⭐ | Jenkinsfile 加 `parallel { ... }` 并行跑登录/购物车/订单三组用例 | 20 分钟 |
| ⭐⭐ | 学 declarative pipeline 全部语法（`when`/`input`/`script`/`withCredentials`） | 1 小时 |
| ⭐ | 看一眼 Jenkinsfile 老语法（Scripted Pipeline）的区别，面试偶尔问 | 30 分钟 |

**别学：** Jenkins 系统管理、JCasC、Kubernetes 集成、Library 框架——测开用不到，**学到 Jenkinsfile + 插件 + 多分支就够找实习**。