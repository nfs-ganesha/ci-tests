// ---------- PIPELINE JOB ----------
pipelineJob('sanity_dev') {

    description('Dynamic CI Test Pipeline with parametrized test suite, topology, repos, and CMake options')

    parameters {

        // Test suite
        choiceParam(
            'TEST_SUITE',
            ['test_fsal'],
            'Select which test suite to run'
        )

        // Server nodes count — only allow 1 or 2
        choiceParam(
            'SERVER_NODE_COUNT',
            ['1', '2'],
            'Number of server nodes to reserve'
        )

        // Client nodes count — only allow 1 or 2
        choiceParam(
            'CLIENT_NODE_COUNT',
            ['1', '2'],
            'Number of client nodes to reserve'
        )

        // CI test repo + branch
        stringParam(
            'CI_REPO',
            'https://github.com/nfs-ganesha/ci-tests.git',
            'Git repo containing CI test framework'
        )
        stringParam(
            'CI_BRANCH',
            'centos-ci',
            'Branch for CI test framework'
        )

        // Ganesha repo + branch
        stringParam(
            'GIT_REPO',
            'https://github.com/nfs-ganesha/nfs-ganesha.git',
            'NFS-Ganesha source repo'
        )
        stringParam(
            'GIT_BRANCH',
            'next',
            'NFS-Ganesha branch'
        )

        // CMake
        stringParam(
            'CMAKE_FLAGS',
            '',
            'Extra CMake flags'
        )
        booleanParam(
            'CMAKE_OVERRIDE',
            false,
            'Override default CMake flags'
        )

        // OS Version
        choiceParam(
            'CENTOS_VERSION',
            ['9s', '10s'],
            'Select CentOS version'
        )

        choiceParam(
            'CENTOS_ARCH',
            ['x86_64'],
            'Architecture'
        )
    }

    definition {
        cpsScm {
            scm {
                git {
                    remote {
                        // Static repo that stores ONLY the Jenkinsfiles
                        url('https://github.com/nfs-ganesha/ci-tests.git')
                    }
                    branch('centos-ci')
                }
            }
            scriptPath('jobs/Jenkinsfile.sanity_dev')
        }
    }
}
