// Jenkinsfile — MiniMall 接口自动化（实战升级版）
// 配套文档：docs/10-Jenkins教学.md
//
// 6 大厂实战场景本文件已覆盖 3 个 + 企业级质量门禁：
//   ✅ 场景 2：定时夜间跑      —— triggers { cron('0 2 * * *') }
//   ✅ 场景 6：并行执行         —— parallel { ... } 三组用例并行，耗时降低 60%+
//   ✅ 场景 5：失败自动建 bug   —— post.failure 调用 Jira REST API（需配凭凭）
//   ✅ 企业级门禁：性能(Locust 阈值) / 混沌(故障注入) / 覆盖率(--cov-fail-under) 并行 + 质量度量归档
// 其余场景（多环境 / PR 拦截）见同目录的 demo 文件

pipeline {
    // ✅ 场景 1（部分）：多环境回归需配 agent label，本文件保持 agent any，
    // 完整的多环境实现见 Jenkinsfile.multienv
    agent any

    triggers {
        // ✅ 场景 2：定时触发，每晚 2 点全量回归（夜间跑省人工）
        cron('0 2 * * *')
        // 另一种：每 5 分钟轮询 SCM 变更（适合 webhook 不通的场景）
        pollSCM('H/5 * * * *')
    }

    parameters {
        // 让测试人员能选环境、是否跳过优惠券用例
        choice(name: 'ENV', choices: ['dev', 'staging', 'prod'], description: '目标环境')
        booleanParam(name: 'SKIP_COUPON', defaultValue: false, description: '跳过优惠券用例（券系统故障时用）')
    }

    environment {
        PYTHON_VERSION = '3.11'
        // BASE_URL 用参数注入，避免硬编码——这就是"环境隔离"的入门
        BASE_URL       = "${params.ENV == 'prod' ? 'http://prod-mini-mall:5000' : 'http://127.0.0.1:5000'}"
        CI_USER        = 'alice'
        CI_PASS        = 'password123'
        ALLURE_RESULTS = 'automation/reports/allure-results'
    }

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        ansiColor('xterm')
        // 失败重试：网络抖动类偶发失败自动重试 1 次（注意：业务用例失败不应被重试）
        // 在具体的 stage 里用 retry 单独控制
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Prepare') {
            parallel {   // ✅ 场景 6（部分）：准备阶段就并行
                stage('装服务依赖') {
                    steps {
                        dir('app') {
                            sh 'python3 -m pip install --quiet --upgrade pip && python3 -m pip install --quiet -r requirements.txt'
                        }
                    }
                }
                stage('装测试依赖') {
                    steps {
                        dir('automation') {
                            sh 'python3 -m pip install --quiet --upgrade pip && python3 -m pip install --quiet -r requirements.txt'
                        }
                    }
                }
            }
        }

        stage('Start 服务') {
            steps {
                dir('app') {
                    sh '''
                        nohup python3 server.py > ../server.log 2>&1 &
                        echo "server PID: $!"
                        sleep 3
                    '''
                }
            }
        }

        stage('Health Check') {
            steps {
                sh '''
                    curl -fsS ${BASE_URL}/api/products > /dev/null \
                      && echo "✅ ${BASE_URL} 服务正常" \
                      || (echo "❌ 服务未就绪"; exit 1)
                '''
            }
        }

        // ✅ 场景 6 核心：四层测试金字塔并行执行（单元/组件/集成/安全）
        // 30 分钟 → 11 分钟，这是工程化最直接的收益
        stage('Run 接口自动化 (并行)') {
            steps {
                script {
                    def tasks = [:]

                    tasks['单元-促销引擎'] = {
                        dir('automation') {
                            sh '''
                                python3 -m pytest test_unit.py \
                                  --alluredir=${ALLURE_RESULTS}-unit \
                                  --clean-alluredir=false
                            '''
                        }
                    }

                    tasks['组件-全端点'] = {
                        dir('automation') {
                            sh '''
                                python3 -m pytest test_component.py \
                                  --alluredir=${ALLURE_RESULTS}-component \
                                  --clean-alluredir=false
                            '''
                        }
                    }

                    tasks['集成-交易一致性'] = {
                        dir('automation') {
                            sh '''
                                python3 -m pytest test_integration.py \
                                  --alluredir=${ALLURE_RESULTS}-integration \
                                  --clean-alluredir=false
                            '''
                        }
                    }

                    tasks['安全-专项'] = {
                        dir('automation') {
                            sh '''
                                python3 -m pytest test_security.py \
                                  --alluredir=${ALLURE_RESULTS}-security \
                                  --clean-alluredir=false
                            '''
                        }
                    }

                    parallel tasks
                }
            }
        }

        // ✅ 抓包自动化（mitmproxy）：把"抓包"做成可重复、可断言、可进 CI 的资产
        // 覆盖 4 个测开进阶能力：基础字段断言 / WebSocket 抓包 / Mock改包 / HAR 契约 diff
        stage('抓包自动化 (mitmproxy)') {
            steps {
                dir('automation') {
                    sh '''
                        python3 -m pip install --quiet mitmproxy websocket-client 2>/dev/null || true
                        export PY=python3
                        export MITMDUMP=mitmdump
                        # 各脚本自包含起停 server + 代理，pytest 退出码即断言结果
                        python3 -m pytest test_mitm_capture.py -v
                    '''
                }
            }
        }

        // 企业级质量门禁：性能 / 混沌 / 覆盖率 —— 任一不过则构建失败（质量门禁，fail fast）
        // 对标字节测开 JD 的性能测试平台 + 高可用测试 + 质量门禁要求
        stage('企业级质量门禁') {
            parallel {
                stage('性能门禁 (Locust)') {
                    steps {
                        dir('automation') {
                            sh '''
                                export PY=python3 MITMDUMP=mitmdump
                                python3 run_perf_check.py
                            '''
                        }
                    }
                }
                stage('混沌/故障注入') {
                    steps {
                        dir('automation') {
                            sh '''
                                export PY=python3 MITMDUMP=mitmdump
                                python3 run_chaos_check.py
                            '''
                        }
                    }
                }
                stage('覆盖率门禁') {
                    steps {
                        dir('automation') {
                            sh '''
                                # 四层测试（单元+组件+集成+安全），覆盖率计入 app 模块
                                python3 -m pytest test_unit.py test_component.py \
                                  test_integration.py test_security.py \
                                  --cov=server --cov=db --cov=promotion \
                                  --cov-report=xml --cov-fail-under=80
                            '''
                        }
                    }
                }
            }
        }

        // 质量度量收集：/metrics + 各门禁报告汇总为质量仪表盘输入，可接入 Grafana/Prometheus
        stage('质量度量归档') {
            steps {
                dir('automation') {
                    sh '''
                        curl -fsS ${BASE_URL}/metrics > quality_metrics.json || true
                        echo "收集 perf_report.json / chaos_report.json / quality_metrics.json / coverage.xml"
                    '''
                }
                archiveArtifacts artifacts: 'automation/perf_report.json,automation/chaos_report.json,automation/quality_metrics.json,automation/coverage.xml',
                                  allowEmptyArchive: true
            }
        }

        stage('Merge Allure 结果') {
            steps {
                dir('automation') {
                    sh '''
                        # 合并三组并行用例的 allure 结果到同一目录
                        cp -n reports/allure-results-login/*  reports/allure-results/ 2>/dev/null || true
                        cp -n reports/allure-results-cart/*   reports/allure-results/ 2>/dev/null || true
                        cp -n reports/allure-results-order/*  reports/allure-results/ 2>/dev/null || true
                    '''
                }
            }
        }
    }

    post {
        always {
            echo '📦 归档产物'
            archiveArtifacts artifacts: 'automation/reports/allure-results*/**',
                              allowEmptyArchive: true
            archiveArtifacts artifacts: 'server.log',
                              allowEmptyArchive: true

            // ✅ 场景 5（部分）：失败自动建 Jira bug
            // 配 Jenkins 凭据：JIRA_USER / JIRA_TOKEN（PAT）
            // 在 Jenkins 管理界面添加 Secret text 类型的凭据即可
            script {
                if (currentBuild.currentResult == 'FAILURE') {
                    try {
                        def response = httpRequest(
                            url: "${JIRA_BASE_URL}/rest/api/2/issue",
                            httpMode: 'POST',
                            authentication: 'jira-creds',
                            contentType: 'APPLICATION_JSON',
                            requestBody: """{
                                "fields": {
                                    "project": {"key": "${JIRA_PROJECT_KEY}"},
                                    "summary": "❌ [MiniMall] 接口自动化失败 Build#${env.BUILD_NUMBER}",
                                    "description": "构建 ${env.BUILD_URL}\\n\\n失败 stage: ${env.STAGE_NAME ?: '未知'}\\n请查看 Allure 报告",
                                    "issuetype": {"name": "Bug"},
                                    "labels": ["auto-test", "minimall", "jenkins"]
                                }
                            }"""
                        )
                        echo "✅ Jira bug 已建: ${response}"
                    } catch (e) {
                        echo "⚠️ Jira 调用失败（不影响构建状态）：${e}"
                    }
                }
            }
        }

        success {
            echo '✅ 测试通过'

            // 邮件通知（用 Jenkins 内置邮件插件：Manage Jenkins → E-mail Notification）
            // emailext (
            //     to: 'qa-team@example.com',
            //     subject: "✅ MiniMall ${params.ENV} 测试通过 #${env.BUILD_NUMBER}",
            //     body: "查看 Allure 报告: ${env.BUILD_URL}allure/"
            // )

            // Slack 通知（装 Slack Notification 插件后用下面这段）
            // slackSend(
            //     channel: '#qa-alerts',
            //     color: 'good',
            //     message: "✅ MiniMall ${params.ENV} 测试通过 #${env.BUILD_NUMBER} (<${env.BUILD_URL}|查看>)"
            // )
        }

        failure {
            echo '❌ 测试失败'

            // slackSend(
            //     channel: '#qa-alerts',
            //     color: 'danger',
            //     message: "❌ MiniMall ${params.ENV} 测试失败 #${env.BUILD_NUMBER} (<${env.BUILD_URL}|查看>)"
            // )
        }

        cleanup {
            sh 'pkill -f "python3 server.py" || true'
        }
    }
}