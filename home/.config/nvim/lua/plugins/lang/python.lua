return {
  {
    "linux-cultist/venv-selector.nvim",
    enabled = true,
    opts = {
      options = {
        picker = "snacks",
        enable_default_searches = true,
        activate_venv_in_terminal = true,
        enable_cache_venvs = true,
        on_telescope_result_callback = function(filepath)
          local env_path = filepath:gsub("/bin/python", "")
          if vim.endswith(env_path, ".venv") then
            return vim.fs.basename(vim.fs.dirname(env_path)) .. " venv"
          end

          return vim.fs.basename(env_path)
        end,
        on_venv_activate_callback = function()
          local venv_name = vim.fs.basename(require("venv-selector").venv())
          if venv_name == ".venv" then
            venv_name = ""
          end
          vim.fn.setenv("CONDA_DEFAULT_ENV", venv_name)
        end,
      },
      search = {
        micromamba = {
          command = "$FD 'bin/python$' $MAMBA_ROOT_PREFIX/envs --full-path --color never",
          type = "anaconda",
        },
      },
    },
  },
  {
    "lualine.nvim",
    optional = true,
    opts = function(_, opts)
      table.insert(opts.sections.lualine_y, "venv-selector")
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
                typeCheckingMode = "base",
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
