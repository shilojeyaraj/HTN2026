from truss_train import definitions
from truss.base import truss_config

deploy_config = definitions.DeployCheckpointsConfig(
    model_name="qwen3-1.7b-command-parser",
    checkpoint_details=definitions.CheckpointList(
        base_model_id="Qwen/Qwen3-1.7B",
        checkpoints=[
            definitions.LoRACheckpoint(
                training_job_id="q4999dw",
                checkpoint_name="checkpoint-105",
                lora_details=definitions.LoRADetails(rank=16),
            )
        ]
    ),
    compute=definitions.Compute(
        accelerator=truss_config.AcceleratorSpec(
            accelerator=truss_config.Accelerator.H100,
            count=1,
        )
    ),
    runtime=definitions.DeployCheckpointsRuntime(
        environment_variables={"HF_TOKEN": definitions.SecretReference(name="hf_access_token")},
    ),
)
