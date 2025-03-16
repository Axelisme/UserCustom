return {
  {
    -- let mamba env can be find by venv-selector.nvim
    -- "linux-cultist/venv-selector.nvim",
    -- branch = "regexp",
    -- enabled = false,
    -- dependencies = { "nvim-telescope/telescope.nvim", lazy = true },
    "stefanboca/venv-selector.nvim",
    branch = "sb/push-rlpxsqmllxtz",
    enabled = true,
    opts = {
      settings = {
        search = {
          cwd = false,
          workspace = false,
          micromamba_envs = {
            command = "$FD 'bin/python$' $MAMBA_ROOT_PREFIX/envs --full-path --color never",
            on_telescope_result_callback = function(filepath)
              return vim.fs.basename(filepath:gsub("/bin/python", ""))
            end,
            type = "anaconda",
          },
        },
      },
    },
  },
  {
    "lualine.nvim",
    optional = true,
    opts = function(_, opts)
      table.insert(opts.sections.lualine_y, {
        function()
          local venv = os.getenv("CONDA_PREFIX")
          if venv ~= nil and string.find(venv, "/") then
            local orig_venv = venv
            for w in orig_venv:gmatch("([^/]+)") do
              venv = w
            end
          end
          return " " .. (venv or "NO ENV")
        end,
        cond = function()
          return vim.bo.filetype == "python"
        end,
      })
    end,
  },
  {
    "neovim/nvim-lspconfig",
    optional = true,
    opts = {
      servers = {
        pyright = {
          settings = {
            python = {
              disableOrganizeImports = true,
              analysis = {
                autoImportCompletions = false,
                diagnosticMode = "openFilesOnly",
                typeCheckingMode = "off",
              },
            },
          },
        },
        basedpyright = {
          settings = {
            basedpyright = {
              disableOrganizeImports = true,
              analysis = {
                autoImportCompletions = false,
                diagnosticMode = "openFilesOnly",
                typeCheckingMode = "off",
                inlayHints = {
                  variableTypes = false,
                  callArgumentsNames = false,
                  functionReturnTypes = true,
                },
              },
            },
          },
        },
      },
    },
  },
}
