from datetime import datetime

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict


class BaseSchema(PydanticBaseModel):
    model_config = ConfigDict(
        use_enum_values=True,
        json_encoders={
            datetime: lambda x: x.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
