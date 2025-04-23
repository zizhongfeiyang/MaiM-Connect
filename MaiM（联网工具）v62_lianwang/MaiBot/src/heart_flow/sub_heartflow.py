from .observation import Observation, ChattingObservation
import asyncio
from src.plugins.moods.moods import MoodManager
from src.plugins.models.utils_model import LLM_request
from src.plugins.config.config import global_config
import re
import time

# from src.plugins.schedule.schedule_generator import bot_schedule
# from src.plugins.memory_system.Hippocampus import HippocampusManager
from src.common.logger import get_module_logger, LogConfig, SUB_HEARTFLOW_STYLE_CONFIG  # noqa: E402

# from src.plugins.chat.utils import get_embedding
# from src.common.database import db
# from typing import Union
from src.individuality.individuality import Individuality
import random
from src.plugins.chat.chat_stream import ChatStream
from src.plugins.person_info.relationship_manager import relationship_manager
from src.plugins.chat.utils import get_recent_group_speaker
from ..plugins.utils.prompt_builder import Prompt, global_prompt_manager

subheartflow_config = LogConfig(
    # 使用海马体专用样式
    console_format=SUB_HEARTFLOW_STYLE_CONFIG["console_format"],
    file_format=SUB_HEARTFLOW_STYLE_CONFIG["file_format"],
)
logger = get_module_logger("subheartflow", config=subheartflow_config)


def init_prompt():
    prompt = ""
    # prompt += f"麦麦的总体想法是：{self.main_heartflow_info}\n\n"
    prompt += "{extra_info}\n"
    # prompt += "{prompt_schedule}\n"
    prompt += "{relation_prompt_all}\n"
    prompt += "{prompt_personality}\n"
    prompt += "刚刚你的想法是{current_thinking_info}。可以适当转换话题\n"
    prompt += "-----------------------------------\n"
    prompt += "现在你正在上网，和qq群里的网友们聊天，群里正在聊的话题是：{chat_observe_info}\n"
    prompt += "你现在{mood_info}\n"
    prompt += "你注意到{sender_name}刚刚说：{message_txt}\n"
    prompt += "现在你接下去继续思考，产生新的想法，不要分点输出，输出连贯的内心独白"
    prompt += "思考时可以想想如何对群聊内容进行回复。回复的要求是：平淡一些，简短一些，说中文，尽量不要说你说过的话\n"
    prompt += "请注意不要输出多余内容(包括前后缀，冒号和引号，括号， 表情，等)，不要带有括号和动作描写"
    prompt += "记得结合上述的消息，生成内心想法，文字不要浮夸，注意你就是{bot_name}，{bot_name}指的就是你。"
    Prompt(prompt, "sub_heartflow_prompt_before")
    prompt = ""
    # prompt += f"你现在正在做的事情是：{schedule_info}\n"
    prompt += "{extra_info}\n"
    prompt += "{prompt_personality}\n"
    prompt += "现在你正在上网，和qq群里的网友们聊天，群里正在聊的话题是：{chat_observe_info}\n"
    prompt += "刚刚你的想法是{current_thinking_info}。"
    prompt += "你现在看到了网友们发的新消息:{message_new_info}\n"
    prompt += "你刚刚回复了群友们:{reply_info}"
    prompt += "你现在{mood_info}"
    prompt += "现在你接下去继续思考，产生新的想法，记得保留你刚刚的想法，不要分点输出，输出连贯的内心独白"
    prompt += "不要太长，但是记得结合上述的消息，要记得你的人设，关注聊天和新内容，关注你回复的内容，不要思考太多:"
    Prompt(prompt, "sub_heartflow_prompt_after")


class CurrentState:
    def __init__(self):
        self.willing = 0
        self.current_state_info = ""

        self.mood_manager = MoodManager()
        self.mood = self.mood_manager.get_prompt()

    def update_current_state_info(self):
        self.current_state_info = self.mood_manager.get_current_mood()


class SubHeartflow:
    def __init__(self, subheartflow_id):
        self.subheartflow_id = subheartflow_id

        self.current_mind = ""
        self.past_mind = []
        self.current_state: CurrentState = CurrentState()
        self.llm_model = LLM_request(
            model=global_config.llm_sub_heartflow,
            temperature=global_config.llm_sub_heartflow["temp"],
            max_tokens=600,
            request_type="sub_heart_flow",
        )

        self.main_heartflow_info = ""

        self.last_reply_time = time.time()
        self.last_active_time = time.time()  # 添加最后激活时间

        if not self.current_mind:
            self.current_mind = "你什么也没想"

        self.is_active = False

        self.observations: list[ChattingObservation] = []

        self.running_knowledges = []

        self.bot_name = global_config.BOT_NICKNAME

    def add_observation(self, observation: Observation):
        """添加一个新的observation对象到列表中，如果已存在相同id的observation则不添加"""
        # 查找是否存在相同id的observation
        for existing_obs in self.observations:
            if existing_obs.observe_id == observation.observe_id:
                # 如果找到相同id的observation，直接返回
                return
        # 如果没有找到相同id的observation，则添加新的
        self.observations.append(observation)

    def remove_observation(self, observation: Observation):
        """从列表中移除一个observation对象"""
        if observation in self.observations:
            self.observations.remove(observation)

    def get_all_observations(self) -> list[Observation]:
        """获取所有observation对象"""
        return self.observations

    def clear_observations(self):
        """清空所有observation对象"""
        self.observations.clear()

    async def subheartflow_start_working(self):
        while True:
            current_time = time.time()
            if (
                current_time - self.last_reply_time > global_config.sub_heart_flow_freeze_time
            ):  # 120秒无回复/不在场，冻结
                self.is_active = False
                await asyncio.sleep(global_config.sub_heart_flow_update_interval)  # 每60秒检查一次
            else:
                self.is_active = True
                self.last_active_time = current_time  # 更新最后激活时间

                self.current_state.update_current_state_info()

                # await self.do_a_thinking()
                # await self.judge_willing()
                await asyncio.sleep(global_config.sub_heart_flow_update_interval)

            # 检查是否超过10分钟没有激活
            if (
                current_time - self.last_active_time > global_config.sub_heart_flow_stop_time
            ):  # 5分钟无回复/不在场，销毁
                logger.info(f"子心流 {self.subheartflow_id} 已经5分钟没有激活，正在销毁...")
                break  # 退出循环，销毁自己

    async def do_observe(self):
        observation = self.observations[0]
        await observation.observe()

    async def do_thinking_before_reply(
        self, message_txt: str, sender_name: str, chat_stream: ChatStream, extra_info: str, obs_id: int = None
    ):
        current_thinking_info = self.current_mind
        mood_info = self.current_state.mood
        # mood_info = "你很生气，很愤怒"
        observation = self.observations[0]
        if obs_id:
            print(f"11111111111有id,开始获取观察信息{obs_id}")
            chat_observe_info = observation.get_observe_info(obs_id)
        else:
            chat_observe_info = observation.get_observe_info()

        extra_info_prompt = ""
        for tool_name, tool_data in extra_info.items():
            extra_info_prompt += f"{tool_name} 相关信息:\n"
            for item in tool_data:
                extra_info_prompt += f"- {item['name']}: {item['content']}\n"

        # 开始构建prompt
        prompt_personality = f"你的名字是{self.bot_name},你"
        # person
        individuality = Individuality.get_instance()

        personality_core = individuality.personality.personality_core
        prompt_personality += personality_core

        personality_sides = individuality.personality.personality_sides
        random.shuffle(personality_sides)
        prompt_personality += f",{personality_sides[0]}"

        identity_detail = individuality.identity.identity_detail
        random.shuffle(identity_detail)
        prompt_personality += f",{identity_detail[0]}"

        # 关系
        who_chat_in_group = [
            (chat_stream.user_info.platform, chat_stream.user_info.user_id, chat_stream.user_info.user_nickname)
        ]
        who_chat_in_group += get_recent_group_speaker(
            chat_stream.stream_id,
            (chat_stream.user_info.platform, chat_stream.user_info.user_id),
            limit=global_config.MAX_CONTEXT_SIZE,
        )

        relation_prompt = ""
        for person in who_chat_in_group:
            relation_prompt += await relationship_manager.build_relationship_info(person)

        # relation_prompt_all = (
        #     f"{relation_prompt}关系等级越大，关系越好，请分析聊天记录，"
        #     f"根据你和说话者{sender_name}的关系和态度进行回复，明确你的立场和情感。"
        # )
        relation_prompt_all = (await global_prompt_manager.get_prompt_async("relationship_prompt")).format(
            relation_prompt, sender_name
        )

        # prompt = ""
        # # prompt += f"麦麦的总体想法是：{self.main_heartflow_info}\n\n"
        # if tool_result.get("used_tools", False):
        #     prompt += f"{collected_info}\n"
        # prompt += f"{relation_prompt_all}\n"
        # prompt += f"{prompt_personality}\n"
        # prompt += f"刚刚你的想法是{current_thinking_info}。如果有新的内容，记得转换话题\n"
        # prompt += "-----------------------------------\n"
        # prompt += f"现在你正在上网，和qq群里的网友们聊天，群里正在聊的话题是：{chat_observe_info}\n"
        # prompt += f"你现在{mood_info}\n"
        # prompt += f"你注意到{sender_name}刚刚说：{message_txt}\n"
        # prompt += "现在你接下去继续思考，产生新的想法，不要分点输出，输出连贯的内心独白"
        # prompt += "思考时可以想想如何对群聊内容进行回复。回复的要求是：平淡一些，简短一些，说中文，尽量不要说你说过的话\n"
        # prompt += "请注意不要输出多余内容(包括前后缀，冒号和引号，括号， 表情，等)，不要带有括号和动作描写"
        # prompt += f"记得结合上述的消息，生成内心想法，文字不要浮夸，注意你就是{self.bot_name}，{self.bot_name}指的就是你。"

        prompt = (await global_prompt_manager.get_prompt_async("sub_heartflow_prompt_before")).format(
            extra_info_prompt,
            # prompt_schedule,
            relation_prompt_all,
            prompt_personality,
            current_thinking_info,
            chat_observe_info,
            mood_info,
            sender_name,
            message_txt,
            self.bot_name,
        )

        try:
            response, reasoning_content = await self.llm_model.generate_response_async(prompt)
        except Exception as e:
            logger.error(f"回复前内心独白获取失败: {e}")
            response = ""
        self.update_current_mind(response)

        self.current_mind = response

        logger.info(f"prompt:\n{prompt}\n")
        logger.info(f"麦麦的思考前脑内状态：{self.current_mind}")
        return self.current_mind, self.past_mind

    async def do_thinking_after_reply(self, reply_content, chat_talking_prompt, extra_info):
        # print("麦麦回复之后脑袋转起来了")

        # 开始构建prompt
        prompt_personality = f"你的名字是{self.bot_name},你"
        # person
        individuality = Individuality.get_instance()

        personality_core = individuality.personality.personality_core
        prompt_personality += personality_core

        extra_info_prompt = ""
        for tool_name, tool_data in extra_info.items():
            extra_info_prompt += f"{tool_name} 相关信息:\n"
            for item in tool_data:
                extra_info_prompt += f"- {item['name']}: {item['content']}\n"

        personality_sides = individuality.personality.personality_sides
        random.shuffle(personality_sides)
        prompt_personality += f",{personality_sides[0]}"

        identity_detail = individuality.identity.identity_detail
        random.shuffle(identity_detail)
        prompt_personality += f",{identity_detail[0]}"

        current_thinking_info = self.current_mind
        mood_info = self.current_state.mood

        observation = self.observations[0]
        chat_observe_info = observation.observe_info

        message_new_info = chat_talking_prompt
        reply_info = reply_content

        prompt = (await global_prompt_manager.get_prompt_async("sub_heartflow_prompt_after")).format(
            extra_info_prompt,
            prompt_personality,
            chat_observe_info,
            current_thinking_info,
            message_new_info,
            reply_info,
            mood_info,
        )

        try:
            response, reasoning_content = await self.llm_model.generate_response_async(prompt)
        except Exception as e:
            logger.error(f"回复后内心独白获取失败: {e}")
            response = ""
        self.update_current_mind(response)

        self.current_mind = response
        logger.info(f"麦麦回复后的脑内状态：{self.current_mind}")

        self.last_reply_time = time.time()

    async def judge_willing(self):
        # 开始构建prompt
        prompt_personality = "你"
        # person
        individuality = Individuality.get_instance()

        personality_core = individuality.personality.personality_core
        prompt_personality += personality_core

        personality_sides = individuality.personality.personality_sides
        random.shuffle(personality_sides)
        prompt_personality += f",{personality_sides[0]}"

        identity_detail = individuality.identity.identity_detail
        random.shuffle(identity_detail)
        prompt_personality += f",{identity_detail[0]}"

        # print("麦麦闹情绪了1")
        current_thinking_info = self.current_mind
        mood_info = self.current_state.mood
        # print("麦麦闹情绪了2")
        prompt = ""
        prompt += f"{prompt_personality}\n"
        prompt += "现在你正在上网，和qq群里的网友们聊天"
        prompt += f"你现在的想法是{current_thinking_info}。"
        prompt += f"你现在{mood_info}。"
        prompt += "现在请你思考，你想不想发言或者回复，请你输出一个数字，1-10，1表示非常不想，10表示非常想。"
        prompt += "请你用<>包裹你的回复意愿，输出<1>表示不想回复，输出<10>表示非常想回复。请你考虑，你完全可以不回复"
        try:
            response, reasoning_content = await self.llm_model.generate_response_async(prompt)
            # 解析willing值
            willing_match = re.search(r"<(\d+)>", response)
        except Exception as e:
            logger.error(f"意愿判断获取失败: {e}")
            willing_match = None
        if willing_match:
            self.current_state.willing = int(willing_match.group(1))
        else:
            self.current_state.willing = 0

        return self.current_state.willing

    def update_current_mind(self, response):
        self.past_mind.append(self.current_mind)
        self.current_mind = response


init_prompt()
# subheartflow = SubHeartflow()
