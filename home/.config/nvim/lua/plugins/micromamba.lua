return {
  {
    -- let mamba env can be find by venv-selector.nvim
    "linux-cultist/venv-selector.nvim",
    ft = "python",
    opts = {
      settings = {
        search = {
          micromamba_envs = {
            command = "$FD 'bin/python$' ~/micromamba/envs --full-path --color never",
            type = "anaconda",
          },
        },
      },
    },
  },
}
